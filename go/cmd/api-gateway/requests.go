// This file contains the handlers for the requests that the API Gateway receives from the client
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/Jorrit05/DYNAMOS/pkg/api"
	"github.com/Jorrit05/DYNAMOS/pkg/lib"
	pb "github.com/Jorrit05/DYNAMOS/pkg/proto"
	"github.com/google/uuid"
	clientv3 "go.etcd.io/etcd/client/v3"
	"go.opencensus.io/trace"
)

const (
	StatusPending = "pending"
	StatusDone    = "done"
	StatusFailed  = "failed"
)

var (
	activeJobID      string
	activeJobLock    sync.Mutex   // to allow only 1 active job at any time
	trainingRequests = sync.Map{} // map[string]TrainingRequestData
	clientsMutex     = &sync.Mutex{}
)

// #region vflTrainModelRequest

type TrainingRequestData struct {
	Status   string
	Results  []map[string]any
	Metadata map[string]any
	// add more fields as needed
}

func getTrainingStatusHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger.Sugar().Info("Starting getTrainingStatusHandler")
		requestID := r.URL.Query().Get("id")
		v, ok := trainingRequests.Load(requestID)
		if !ok {
			http.Error(w, "Request ID not found", http.StatusNotFound)
			return
		}

		logger.Sugar().Debug("Found training request: ", requestID)
		reqData := v.(TrainingRequestData)
		resp := map[string]any{
			"request_id": requestID,
			"status":     reqData.Status,
			"metadata":   reqData.Metadata,
			"results":    reqData.Results,
		}
		respBytes, _ := json.MarshalIndent(resp, "", "    ")
		w.WriteHeader(http.StatusOK)
		w.Write(respBytes)
	}
}

func requestHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		activeJobLock.Lock()
		defer activeJobLock.Unlock()

		// Check for existing active job
		if activeJobID != "" {
			v, _ := trainingRequests.Load(activeJobID)
			reqData := v.(TrainingRequestData)
			resp := map[string]any{
				"error":             "A training job is already in progress.",
				"active_request_id": activeJobID,
				"active_status":     reqData.Status,
			}
			respBytes, _ := json.Marshal(resp)
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write(respBytes)
			return
		}

		// Accept new job
		requestID := uuid.New().String()
		activeJobID = requestID
		reqData := TrainingRequestData{
			Status: StatusPending,
			Metadata: map[string]any{
				"created_at": time.Now().Format(time.RFC3339),
			},
			Results: []map[string]any{},
		}
		trainingRequests.Store(requestID, reqData)

		resp := map[string]any{
			"request_id": requestID,
			"status":     StatusPending,
		}

		logger.Sugar().Info("Accepted new job with id: ", activeJobID)

		// Parse the request body
		body, err := api.GetRequestBody(w, r, serviceName)
		if err != nil {
			return
		}

		var apiReqApproval api.RequestApproval
		if err := json.Unmarshal(body, &apiReqApproval); err != nil {
			logger.Sugar().Errorf("Error unmMarshalling get apiReqApproval: %v", err)
			return
		}

		userPb := &pb.User{
			Id:       apiReqApproval.User.Id,
			UserName: apiReqApproval.User.UserName,
		}

		var dataRequestInterface map[string]any
		if err := json.Unmarshal(apiReqApproval.DataRequest, &dataRequestInterface); err != nil {
			logger.Sugar().Errorf("Error unmarhsalling get request: %v", err)
			return
		}

		dataRequestOptions := &api.DataRequestOptions{}
		dataRequestOptions.Options = make(map[string]bool)
		if err := json.Unmarshal(apiReqApproval.DataRequest, &dataRequestOptions); err != nil {
			logger.Sugar().Errorf("Error unmMarshalling get apiReqApproval: %v", err)
			return
		}

		dataRequestInterface["user"] = userPb

		// Create protobuf struct for the req approval flow
		protoRequest := &pb.RequestApproval{
			Type:             apiReqApproval.Type,
			User:             userPb,
			DataProviders:    apiReqApproval.DataProviders,
			DestinationQueue: "policyEnforcer-in",
			Options:          dataRequestOptions.Options,
		}

		respBytes, _ := json.Marshal(resp)
		w.WriteHeader(http.StatusAccepted)
		w.Write(respBytes)

		// ---- TRIGGER TRAINING IN BACKGROUND ----
		go func() {
			startTraining(protoRequest, dataRequestInterface, apiReqApproval, r, requestID)
		}()

	}
}

func startTraining(protoRequest *pb.RequestApproval, dataRequestInterface map[string]any, apiReqApproval api.RequestApproval, r *http.Request, requestID string) {
	logger.Debug("Starting training process...")
	// Requests may take up to 10 minutes now
	ctxWithTimeout, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	// Start a new span with the context that has a timeout
	ctx, span := trace.StartSpan(ctxWithTimeout, "requestApprovalHandler")
	defer span.End()

	// Create a channel to receive the response
	responseChan := make(chan validation)

	requestApprovalMutex.Lock()
	requestApprovalMap[protoRequest.User.Id] = responseChan
	requestApprovalMutex.Unlock()

	_, err := c.SendRequestApproval(ctx, protoRequest)
	if err != nil {
		logger.Sugar().Errorf("error in sending requestapproval: %v", err)
	}

	select {
	case validationStruct := <-responseChan:
		msg := validationStruct.response

		logger.Sugar().Infof("Received response, %s", msg.Type)
		if msg.Type != "requestApprovalResponse" {
			logger.Sugar().Errorf("Unexpected message received, type: %s", msg.Type)
			// http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		requestMetadata := &pb.RequestMetadata{
			JobId: msg.JobId,
		}
		dataRequestInterface["requestMetadata"] = requestMetadata

		logger.Sugar().Infof("Data Prepared jsonData: %s", dataRequestInterface)

		var response []byte

		if apiReqApproval.Type == "vflTrainModelRequest" {
			ctxWithoutCancel := context.WithoutCancel(r.Context())
			response = runVFLTraining(dataRequestInterface, msg.AuthorizedProviders, msg.JobId, ctxWithoutCancel, requestID)

		} else {
			// Marshal the combined data back into JSON for forwarding
			dataRequestJson, err := json.Marshal(dataRequestInterface)
			if err != nil {
				logger.Sugar().Errorf("Error marshalling combined data: %v", err)
				return
			}

			response = sendDataToAuthProviders(dataRequestJson, msg.AuthorizedProviders, apiReqApproval.Type, msg.JobId)
		}

		// w.WriteHeader(http.StatusOK)
		// w.Write(response)
		logger.Sugar().Info("Training process completed for request id: ", requestID)
		logger.Sugar().Info("Response: ", string(response))
		return

	case <-ctx.Done():
		// http.Error(w, "Request timed out", http.StatusRequestTimeout)
		return
	}

}

func runVFLTrainingRound(dataRequest map[string]any, clients []ClientData, serverAuth string, serverUrl string, learning_rate float64, trainingBacktrack int64, communication_frequency int64, sample_batch_size int64) ([]float64, error) {
	var wg sync.WaitGroup
	responses := map[string]string{}
	var existingError error = nil
	var sample_batch_indexes string
	formattedEndpoint := "http://%s:8080/agent/v1/vflTrainRequest/%s"

	serverTarget := strings.ToLower(serverAuth)
	serverEndpoint := fmt.Sprintf(formattedEndpoint, serverUrl, serverTarget)

	// Step 1: Send server for sample
	logger.Sugar().Info("[SERVER] [vflSampleBatchRequest] Requesting mini-batch samples")
	dataRequest["type"] = "vflSampleBatchRequest"
	dataRequest["data"] = map[string]any{
		"sample_batch_size": sample_batch_size,
	}

	responseData, err := sendRequest(serverEndpoint, dataRequest)

	if err != nil {
		logger.Sugar().Errorf("Error sending data, %v", err)
	} else {
		sample_batch_indexes = responseData.Data.AsMap()["sample_batch_indexes"].(string)
	}

	logger.Sugar().Info("[SERVER] [vflSampleBatchRequest] Response OK")

	// Step 2: Send the samples to clients to get the intermediate embeddings.
	for _, client := range clients {
		auth := client.Auth
		url := client.Url

		logger.Sugar().Info("[", auth, "] [vflTrainRequest] Requesting intermediate embeddings at url: ", url)

		wg.Add(1)
		target := strings.ToLower(auth)

		ips, err := net.LookupIP(url)
		if err == nil && len(ips) != 0 {
			url = ips[0].String()
		}

		endpoint := fmt.Sprintf(formattedEndpoint, url, target)

		go func() {
			dataRequest["type"] = "vflTrainRequest"
			dataRequest["data"] = map[string]any{
				"sample_batch_indexes": sample_batch_indexes,
			}

			responseData, err := sendRequest(endpoint, dataRequest)
			if err != nil {
				existingError = err
				logger.Sugar().Errorf("Error sending data, %v", err)
			} else {
				dataJson := responseData.Data.AsMap()
				embeddings, ok := dataJson["embeddings"].(string)

				if !ok {
					logger.Sugar().Error("No embeddings found in the return data.")
					embeddings = ""
					// TODO: Handle disagreements?
				}

				responses[target] = embeddings
			}

			wg.Done()
			logger.Sugar().Info("[", auth, "] [vflTrainRequest] Response OK")
		}()
	}

	wg.Wait()

	if existingError != nil {
		return []float64{}, existingError
	}

	logger.Sugar().Info("[SERVER] [vflAggregateRequest] Sending the embeddings to server to calculate gradients")

	// Collect embeddings from all clients
	// There is a major bug here with the ordering and the way server receives the embeddings.
	logger.Sugar().Info("[SERVER] Check embeddings ordering")
	embeddingList := []string{}
	for _, client := range clients {
		if emb, ok := responses[strings.ToLower(client.Auth)]; ok {
			embeddingList = append(embeddingList, emb)
		}

		logger.Sugar().Debug("Embeddings for: ", client.Auth)
	}

	logger.Sugar().Debug("The embeddings list: ", embeddingList)

	// Step 3: Send intermediate embeddings to server to calculate gradients
	dataRequest["type"] = "vflAggregateRequest"
	dataRequest["data"] = map[string]any{
		"embeddings":        embeddingList,
		"trainingBacktrack": trainingBacktrack,
	}

	serverResponse, err := sendRequest(serverEndpoint, dataRequest)
	if err != nil {
		logger.Sugar().Error("Unmarshalling response did not go well: ", err)
		return []float64{}, err
	}

	// accuracy := serverResponse.Data.GetFields()["accuracy"].GetNumberValue()
	gradientList := serverResponse.Data.GetFields()["gradients"].GetListValue().GetValues()

	gradients := []string{}
	for _, val := range gradientList {
		gradients = append(gradients, val.GetStringValue())
	}

	logger.Sugar().Info("[SERVER] [vflAggregateRequest] Gradients received OK")

	// Step 4: Given the gradients, the clients perform gradient descent.
	index := 0
	for _, client := range clients {
		auth := client.Auth
		url := client.Url

		wg.Add(1)
		target := strings.ToLower(auth)
		endpoint := fmt.Sprintf(formattedEndpoint, url, target)

		logger.Sugar().Info("[", target, "] [vflGradientDescentRequest] Perform gradient descent for ", communication_frequency, " times")

		go func() {
			dataRequest["type"] = "vflGradientDescentRequest"
			dataRequest["data"] = map[string]any{
				"gradients":               gradients[index],
				"learning_rate":           learning_rate,
				"communication_frequency": communication_frequency,
			}

			index++

			response, err := sendRequest(endpoint, dataRequest)
			if err != nil {
				existingError = err
				logger.Sugar().Error("Error sending data, ", err, ", received: ", response)
			}
			wg.Done()
			logger.Sugar().Info("[", target, "] [vflGradientDescentRequest] Response OK")
		}()
	}

	accuracies := []float64{}

	logger.Sugar().Info("[SERVER] [vflLocalUpdateRequest] Perform local update for ", communication_frequency, " times")

	// Step 5: Server as well perform local update on its model given the intermediate embeddings.
	serverDataRequest := map[string]any{}

	// Copy it for now.
	for key, value := range dataRequest {
		serverDataRequest[key] = value
	}

	serverDataRequest["type"] = "vflLocalUpdateRequest"
	serverDataRequest["data"] = map[string]any{
		"embeddings":              embeddingList,
		"trainingBacktrack":       trainingBacktrack,
		"communication_frequency": communication_frequency,
	}

	serverResponse, err = sendRequest(serverEndpoint, serverDataRequest)
	if err != nil {
		logger.Sugar().Error("Unmarshalling response did not go well: ", err)
	} else {
		accuraciesList := serverResponse.Data.GetFields()["accuracies"].GetListValue().GetValues()

		for _, val := range accuraciesList {
			accuracies = append(accuracies, val.GetNumberValue())
		}
	}

	logger.Sugar().Info("[SERVER] [vflLocalUpdateRequest] Response 0K")

	wg.Wait()

	if existingError != nil {
		return []float64{}, existingError
	}

	return accuracies, nil
}

func extractValueOrDefault[T ~int64 | ~float64](data map[string]any, propertyName string, defaultValue T) T {
	value, ok := data[propertyName].(float64)
	if ok {
		return T(value)
	}

	logger.Sugar().Debug("Property [", propertyName, "] wasn't found on the request parameters. Default value [", defaultValue, "] is going to be used instead.")
	return defaultValue
}

// #endregion

func getSafeClients(clients *[]ClientData) []ClientData {
	clientsMutex.Lock()
	currentClients := make([]ClientData, len(*clients))
	copy(currentClients, *clients)
	clientsMutex.Unlock()

	return currentClients
}

func checkPolicyUpdate(clients *[]ClientData, user *pb.User) {
	policyUpdateChan := make(chan PolicyUpdateResponse)

	// There is a misalignment because there are static User.Ids in different parts of the code.
	// This has to be changed in the future.
	logger.Sugar().Debug("Updating policyUpdateMap with key: ", user.Id)
	policyUpdateMutex.Lock()
	policyUpdateMap[user.Id] = policyUpdateChan
	policyUpdateMutex.Unlock()

	go func() {

		for policyUpdateResponse := range policyUpdateChan {
			availableProviders, err := getAvailableProviders()

			logger.Sugar().Debug("The available providers are: ", availableProviders)

			if err != nil {
				logger.Sugar().Errorf("A problem occurred while fetching providers GetAvailableProviders: ", err)
			}

			validDataproviders := policyUpdateResponse.GetValidDataproviders()

			if len(*clients) != len(availableProviders) {
				logger.Sugar().Debug("Clients before policy update: ", clients)

				var activeClients []ClientData
				for auth, agentDetail := range availableProviders {
					if strings.ToLower(auth) == "server" {
						continue
					}

					_, exists := validDataproviders[auth]

					if !exists {
						continue
					}

					activeClients = append(activeClients, ClientData{
						Auth: auth,
						Url:  agentDetail.Dns,
					})
				}

				clientsMutex.Lock()
				*clients = activeClients
				clientsMutex.Unlock()
				logger.Sugar().Debug("Clients after policy update: ", clients)
			}
		}

		policyUpdateMutex.Lock()
		delete(policyUpdateMap, user.Id)
		policyUpdateMutex.Unlock()
	}()
}

type ClientData struct {
	Auth string
	Url  string
}

func runVFLTraining(dataRequest map[string]any, authorizedProviders map[string]string, jobId string, ctx context.Context, requestID string) []byte {
	clients := &[]ClientData{}
	var serverUrl string
	var serverAuth string
	var finalAccuracy float64
	var wg sync.WaitGroup

	// Default parameters values
	var sample_batch_size int64 = 64
	var communication_frequency int64 = 10
	var cycles int64 = 10
	var learning_rate float64 = 0.05
	var policy_removal int64 = -1
	var policy_reintroduction int64 = -1
	var dataProviders []string = []string{}

	var trainingBacktrack int64 = 0 // Default value

	data, ok := dataRequest["data"].(map[string]any)
	logger.Sugar().Info("Data from req: ", data)

	if ok {
		// Parameters extraction
		sample_batch_size = extractValueOrDefault(data, "sample_batch_size", sample_batch_size)
		communication_frequency = extractValueOrDefault(data, "communication_frequency", communication_frequency)
		cycles = extractValueOrDefault(data, "cycles", cycles)
		learning_rate = extractValueOrDefault(data, "learning_rate", learning_rate)
		trainingBacktrack = extractValueOrDefault(data, "training_backtrack", trainingBacktrack)
		policy_removal = extractValueOrDefault(data, "policy_removal", policy_removal)
		policy_reintroduction = extractValueOrDefault(data, "policy_reintroduction", policy_reintroduction)
	}

	metadata := map[string]any{
		"total_rounds":          cycles,
		"policy_removal":        policy_removal,
		"training_backtrack":    trainingBacktrack,
		"policy_reintroduction": policy_reintroduction,
	}

	// logger.Sugar().Debug("metadata: ", metadata)

	var results []map[string]any
	trainingFailed := false

	for auth, url := range authorizedProviders {
		if strings.ToLower(auth) == "server" {
			serverUrl = url
			serverAuth = auth
		} else if url != "" {
			*clients = append(*clients, ClientData{Auth: auth, Url: url})
		}

		dataProviders = append(dataProviders, auth)
	}

	logger.Sugar().Info("Sending ping to start pods...")
	dataRequest["type"] = "vflPingRequest"

	dataRequestJson, err := json.Marshal(dataRequest)
	if err != nil {
		logger.Sugar().Errorf("Error marshalling combined data: %v", err)
		return []byte{}
	}

	user, ok := dataRequest["user"].(*pb.User)

	if !ok {
		logger.Sugar().Info("Did not retrieve User from dataRequest, cannot dynamically verify each training round.")
		user = &pb.User{}
	}

	var noPing bool = false

	for auth, url := range authorizedProviders {
		wg.Add(1)
		target := strings.ToLower(auth)
		endpoint := fmt.Sprintf("http://%s:8080/agent/v1/vflTrainRequest/%s", url, target)

		go func() {
			// TODO: Repeat ping until no error, after 5 tries, cancel request
			for i := range 5 {
				_, err := sendData(endpoint, dataRequestJson)

				if err == nil {
					break
				}

				if i == 4 {
					noPing = true
				}
			}

			wg.Done()
		}()
	}

	// note: this is likely misplaced, probably needs to be after the wait
	if noPing {
		logger.Sugar().Error("No ping from a client or the server. Something is wrong.")
	}

	wg.Wait()

	// Checks if policy changes (from incoming messages)
	checkPolicyUpdate(clients, user)

	iterations := cycles / communication_frequency
	policyRemovalRound := int64(-1)
	if policy_removal != -1 {
		policyRemovalRound = policy_removal / communication_frequency
	}

	policyReintroductionRound := int64(-1)
	if policy_reintroduction != -1 {
		policyReintroductionRound = policy_reintroduction / communication_frequency
	}

	logger.Sugar().Info("Running VFL for ", cycles, " rounds")
	for round := range iterations {
		logger.Sugar().Info("Running VFL training round ", round)

		currentClients := getSafeClients(clients)

		numClients := -1          // default value in case of error
		metadata_accuracy := -1.0 // default value in case of error

		// TODO: Implement policy change request
		if policyRemovalRound == round {
			logger.Sugar().Info("Sending in the policy change request, removing client 3 from the agreement.")
			logger.Sugar().Info("TODO: Policy change request not yet implemented.")

			api.DeleteRequest(
				"http://orchestrator.orchestrator.svc.cluster.local:8080/api/v1/policyEnforcer/agreements/clientthree",
				"",
				nil)
		}

		// TODO: Implement policy change request
		if policyReintroductionRound == round {
			logger.Sugar().Info("Sending in the policy change request, reintroducing client 3 to the agreement.")
			logger.Sugar().Info("TODO: Policy change request not yet implemented. (values are hardcoded)")

			rawPayload := `{
						"name": "clientthree"
						,
						"relations": {
							"evangelos.pipilikas@student.uva.nl": {
								"ID": "GUID",
								"requestTypes": [
									"vflTrainRequest"
								],
								"dataSets": null,
								"allowedArchetypes": [
									"computeToData"
								],
								"allowedComputeProviders": [
									"clientthree"
								]
							}
						},
						"computeProviders": [
							"clientthree"
						],
						"archetypes": [
							"computeToData"
						]
				}`

			api.PutRequest(
				"http://orchestrator.orchestrator.svc.cluster.local:8080/api/v1/policyEnforcer",
				rawPayload,
				nil)
		}

		logger.Sugar().Debug("Clients: ", currentClients)
		numClients = len(currentClients)

		logger.Sugar().Info("- Sending training request")
		accuracies, err := runVFLTrainingRound(dataRequest, currentClients, serverAuth, serverUrl, learning_rate, trainingBacktrack, communication_frequency, sample_batch_size)
		logger.Sugar().Info("- Intermediate accuracy achieved: ", accuracies[len(accuracies)-1], " for round ", round)
		finalAccuracy = accuracies[len(accuracies)-1]
		metadata_accuracy = accuracies[len(accuracies)-1] // store accuracy from metadata for results

		if err != nil {
			logger.Sugar().Error("Training round returned an error.")
			trainingFailed = true
			break
		}

		// This has to be changed.
		result := map[string]any{
			"timestamp":   time.Now().Format(time.RFC3339),
			"train_round": round,
			"accuracy":    metadata_accuracy,
			"clients":     numClients,
		}
		results = append(results, result)
		v, _ := trainingRequests.Load(requestID)
		reqData := v.(TrainingRequestData)
		reqData.Results = results
		trainingRequests.Store(requestID, reqData)

		if trainingFailed {
			break
		}

	}

	logger.Sugar().Info("-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-")
	logger.Sugar().Info("Final accuracy achieved: ", finalAccuracy)
	logger.Sugar().Info("-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-")

	dataRequest["type"] = "vflShutdownRequest"

	dataRequestJson, err = json.Marshal(dataRequest)
	if err != nil {
		logger.Sugar().Errorf("Error marshalling combined data: %v", err)
		return []byte{}
	}

	for auth, url := range authorizedProviders {
		wg.Add(1)
		target := strings.ToLower(auth)
		endpoint := fmt.Sprintf("http://%s:8080/agent/v1/vflTrainRequest/%s", url, target)

		go func() {
			sendData(endpoint, dataRequestJson)
			wg.Done()
		}()
	}

	wg.Wait()

	response := map[string]any{
		"jobId":    jobId,
		"accuracy": finalAccuracy,
	}

	logger.Sugar().Info("-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-")
	logger.Sugar().Info("Final accuracy achieved: ", finalAccuracy)
	logger.Sugar().Info("-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-")

	new_response := map[string]any{
		"metadata": metadata,
		"results":  results,
	}

	// --- SET STATUS and UNLOCK ---
	v, ok := trainingRequests.Load(requestID)
	if ok {
		reqData := v.(TrainingRequestData)
		reqData.Metadata = metadata
		if trainingFailed {
			reqData.Status = StatusFailed
		} else {
			reqData.Status = StatusDone
		}
		trainingRequests.Store(requestID, reqData)
		logger.Sugar().Infow("Job completed", "requestID", requestID, "status", reqData.Status, "accuracy", finalAccuracy)
	} else {
		logger.Sugar().Error("Could not find the training request to update status.")
	}

	// Release the active job lock
	activeJobLock.Lock()
	activeJobID = ""
	activeJobLock.Unlock()

	// Marshal and return
	responseJson, err := json.MarshalIndent(new_response, "", "    ")
	if err != nil {
		logger.Sugar().Errorf("Error marshalling training results: %v", err)
		return []byte{}
	}

	logger.Sugar().Info("Training results: ", string(responseJson))
	return cleanupAndMarshalResponse(response) // note this is not the same as responseJson
}

// #region vflTrainModelRequest - Helpers

func sendRequest(endpoint string, dataRequest map[string]any) (*pb.MicroserviceCommunication, error) {
	dataRequestJson, err := json.Marshal(dataRequest)
	if err != nil {
		logger.Sugar().Errorf("Error marshalling combined data: %v", err)
		return nil, err
	}

	responseData, err := sendData(endpoint, dataRequestJson)
	if err != nil {
		logger.Sugar().Errorf("Error sending data to the server, %v", err)
	}

	serverResponse := &pb.MicroserviceCommunication{}
	err = json.Unmarshal([]byte(responseData), serverResponse)

	responseObj := &pb.MicroserviceCommunication{}
	if err := json.Unmarshal([]byte(responseData), responseObj); err != nil {
		return nil, fmt.Errorf("Error unmarshalling response: %w", err)
	}

	return responseObj, nil
}

// #endregion

// Use the data request that was previously built and send it to the authorised providers
// acquired from the request approval
func sendDataToAuthProviders(dataRequest []byte, authorizedProviders map[string]string, msgType string, jobId string) []byte {
	// Setup the wait group for async data requests
	var wg sync.WaitGroup
	var responses []string

	// This will be replaced with AMQ in the future
	agentPort := "8080"
	// Iterate over each auth provider
	for auth, url := range authorizedProviders {
		wg.Add(1)
		target := strings.ToLower(auth)
		// Construct the end point
		endpoint := fmt.Sprintf("http://%s:%s/agent/v1/%s/%s", url, agentPort, msgType, target)

		logger.Sugar().Infof("Sending request to %s.\nEndpoint: %s\nJSON:%v", target, endpoint, string(dataRequest))

		// Async call send the data
		go func() {
			respData, err := sendData(endpoint, dataRequest)
			if err != nil {
				logger.Sugar().Errorf("Error sending data, %v", err)
			}
			responses = append(responses, respData)
			// Signal that the data request has been sent to all auth providers
			wg.Done()
		}()
	}

	// Wait until all the requests are complete
	wg.Wait()
	logger.Sugar().Debug("Returning responses")

	responseMap := map[string]any{
		"jobId":     jobId,
		"responses": responses,
	}

	// jsonResponse, _ := json.Marshal(responseMap)
	// return jsonResponse
	return cleanupAndMarshalResponse(responseMap)
}

// Now assumes input is map[string]interface{} and directly marshals it to prettified JSON.
func cleanupAndMarshalResponse(responseMap map[string]any) []byte {
	prettifiedJSON, err := json.MarshalIndent(responseMap, "", "    ")
	if err != nil {
		logger.Sugar().Errorf("Error marshalling cleaned response: %v", err)
	}
	return prettifiedJSON
}

func sendData(endpoint string, jsonData []byte) (string, error) {
	// FIXME: Change to an actual token in the future?
	headers := map[string]string{
		"Authorization": "bearer 1234",
	}
	body, err := api.PostRequest(endpoint, string(jsonData), headers)
	if err != nil {
		return "", err
	}

	return string(body), nil
}

func availableProvidersHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger.Debug("Starting requestApprovalHandler")
		var availableProviders = make(map[string]lib.AgentDetails)
		resp, err := getAvailableProviders()
		if err != nil {
			logger.Sugar().Errorf("Error getting available providers: %v", err)
			return
		}

		// Bind resp to availableProviders
		availableProviders = resp

		jsonResponse, err := json.Marshal(availableProviders)
		if err != nil {
			logger.Sugar().Errorf("Error marshalling result, %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusOK)
		w.Write(jsonResponse)
	}
}

// Maybe this should be moved into the orchestrarot
func getAvailableProviders() (map[string]lib.AgentDetails, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Get the value from etcd.
	resp, err := etcdClient.Get(ctx, "/agents/online", clientv3.WithPrefix())
	if err != nil {
		logger.Sugar().Errorf("failed to get value from etcd: %v", err)
		return nil, err
	}

	// Initialize an empty map to store the unmarshaled structs.
	result := make(map[string]lib.AgentDetails)
	// Iterate through the key-value pairs and unmarshal the values into structs.
	for _, kv := range resp.Kvs {
		var target lib.AgentDetails
		err = json.Unmarshal(kv.Value, &target)
		if err != nil {
			// return nil, fmt.Errorf("failed to unmarshal JSON for key %s: %v", key, err)
		}
		result[string(target.Name)] = target
	}

	return result, nil

}
