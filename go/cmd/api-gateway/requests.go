// This file contains the handlers for the requests that the API Gateway receives from the client
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"maps"
	"net/http"
	"strings"
	"sync"
	"time"

	"slices"

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

// Provider names
const (
	Authority  = "authority"
	Aggregator = "aggregator"
	Server     = "server"
)

var (
	activeJobID       string
	activeJobLock     sync.Mutex   // to allow only 1 active job at any time
	trainingRequests  = sync.Map{} // map[string]TrainingRequestData
	formattedEndpoint = "http://%s:8080/agent/v1/vflTrainRequest/%s"
	cyclesCompleted   int64
	clientsMutex      = &sync.Mutex{}
	excludedClients   = []string{Authority, Aggregator}
)

// #region TrainingRequestData helpers

type TrainingRequestData struct {
	Status   string
	Results  []map[string]any
	Metadata map[string]any
	// add more fields as needed
}

func getTrainingRequest(jobId string) (TrainingRequestData, bool) {
	v, ok := trainingRequests.Load(jobId)
	if !ok {
		logger.Sugar().Debug("Not found training request: ", jobId)
		return TrainingRequestData{}, false
	}

	return v.(TrainingRequestData), true
}

func addAndUpdateTrainingRequest(jobId string, cycle int64, clientsNumber int, accuracy float64) {
	result := map[string]any{
		"timestamp":   time.Now().Format(time.RFC3339),
		"train_round": cycle,
		"accuracy":    accuracy,
		"clients":     clientsNumber,
	}

	reqData, _ := getTrainingRequest(jobId)

	if reqData.Results == nil {
		reqData.Results = make([]map[string]any, 0)
	}

	reqData.Results = append(reqData.Results, result)
	trainingRequests.Store(jobId, reqData)
}

// #endregion

func getTrainingStatusHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger.Sugar().Info("Starting getTrainingStatusHandler")
		requestID := r.URL.Query().Get("id")
		reqData, ok := getTrainingRequest(requestID)
		if !ok {
			http.Error(w, "Request ID not found", http.StatusNotFound)
			return
		}

		logger.Sugar().Debug("Found training request: ", requestID)
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

func cloneDataRequest(dataRequest map[string]any, requestType string, data map[string]any) map[string]any {
	request := maps.Clone(dataRequest)
	request["type"] = requestType
	request["data"] = data
	return request
}

func cloneAndSendDataRequest(dataRequest map[string]any, authorizedProviders map[string]string, auth string, requestType string, data map[string]any) (*pb.MicroserviceCommunication, error) {
	_, endpoint := findAuthorizedProvider(authorizedProviders, auth)

	logger.Sugar().Debug("[", auth, "] [", requestType, "] Sending request...")
	request := cloneDataRequest(dataRequest, requestType, data)

	responseData, err := sendRequest(endpoint, request)

	if err != nil {
		logger.Sugar().Errorf("Error sending data, %v", err)
	} else {
		keys := make(map[string]string)

		for k, v := range responseData.Data.GetFields() {
			keys[k] = fmt.Sprintf("%T", v.Kind)
		}

		logger.Sugar().Debug("[", auth, "] [", requestType, "] Response: ", keys)
	}

	return responseData, err
}

func getSafeClients(clients *[]ClientData) []ClientData {
	clientsMutex.Lock()
	currentClients := make([]ClientData, len(*clients))
	copy(currentClients, *clients)
	clientsMutex.Unlock()

	return currentClients
}

func findAuthorizedProvider(authorizedProviders map[string]string, targetedAuth string) (string, string) {
	loweredTargetedAuth := strings.ToLower(targetedAuth)

	for auth, url := range authorizedProviders {
		target := strings.ToLower(auth)

		if target == loweredTargetedAuth {
			return auth, fmt.Sprintf(formattedEndpoint, url, target)
		}
	}

	return "", ""
}

type ClientFeature struct {
	PartyId      string `json:"party_id"`
	FeaturesSize any    `json:"features_size"`
}

func initializeVFLServices(dataRequest map[string]any, clients []ClientData, weights *[]any, authorizedProviders map[string]string, sampleBatchSize int64) error {

	// Initialize authority
	responseData, err := cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Authority,
		"vflInitializeRequest",
		map[string]any{
			"parties_size": len(clients),
			"batch_size":   sampleBatchSize,
		},
	)

	if err != nil {
		return err
	}

	encryptionKeys := responseData.Data.GetFields()["mife_encryption_keys"].GetListValue().GetValues()
	sifePublicKey := responseData.Data.GetFields()["sife_public_key"].GetStringValue()
	mifePublicKey := responseData.Data.GetFields()["mife_public_key"].GetStringValue()

	// Initialize parties
	var wg sync.WaitGroup
	var mtx sync.Mutex
	featuresSize := map[string]any{}

	for index, client := range clients {
		wg.Add(1)

		go func() {
			defer wg.Done()

			responseData, err := cloneAndSendDataRequest(dataRequest, authorizedProviders,
				client.Auth,
				"vflInitializeRequest",
				map[string]any{
					"mife_encryption_key": encryptionKeys[index],
					"sife_public_key":     sifePublicKey,
				},
			)

			if err == nil {
				v := responseData.Data.GetFields()["features_size"].GetNumberValue()
				if v != 0 {
					mtx.Lock()
					featuresSize[client.Auth] = v
					mtx.Unlock()
				}
			}
		}()
	}

	wg.Wait()

	orderedClientFeatures := []ClientFeature{}

	logger.Sugar().Debug("Clients: ", clients)

	for _, client := range clients {
		if size, exists := featuresSize[client.Auth]; exists {
			orderedClientFeatures = append(orderedClientFeatures, ClientFeature{
				PartyId:      client.Auth,
				FeaturesSize: size,
			})
		}
	}

	// Initialize aggregator
	responseData, err = cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Aggregator,
		"vflInitializeRequest",
		map[string]any{
			"parties_size":     len(clients),
			"batch_size":       sampleBatchSize,
			"mife_public_key":  mifePublicKey,
			"sife_public_key":  sifePublicKey,
			"parties_features": orderedClientFeatures,
		},
	)

	if err != nil {
		return err
	}

	*weights = ToAnyList(responseData.Data.GetFields()["weights"].GetListValue().GetValues())

	return nil
}

func ToAnyList[T any](input []T) []any {
	result := make([]any, len(input))
	for i, v := range input {
		result[i] = v
	}
	return result
}

func runVFLTrainingRound(dataRequest map[string]any, clients []ClientData, weights *[]any, authorizedProviders map[string]string, sampleBatchSize int64) (float64, float64, error) {

	responseData, err := cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Server,
		"vflSampleBatchRequest",
		map[string]any{
			"sample_batch_size": sampleBatchSize,
		},
	)

	if err != nil {
		return 0., 0., err
	}

	sampleBatchIndexes := responseData.Data.GetFields()["sample_batch_indexes"].GetStringValue()

	var wg sync.WaitGroup

	featureDimension := map[string]any{}
	sampleDimension := map[string]any{}

	index := 0

	for _, client := range clients {
		wg.Add(1)

		weightIndex := -1
		// Server holds only labels. No weights.
		if strings.ToLower(client.Auth) != Server {
			weightIndex = index
			index++
		}

		go func(idx int) {
			defer wg.Done()

			data := map[string]any{
				"sample_batch_indexes": sampleBatchIndexes,
			}

			if weightIndex != -1 {
				data["weights"] = (*weights)[idx]
			}

			responseData, err := cloneAndSendDataRequest(dataRequest, authorizedProviders,
				client.Auth,
				"vflExtractCiphertextsRequest",
				data,
			)

			if err != nil {
				logger.Sugar().Error("")
			}

			featureDimension[client.Auth] = responseData.Data.GetFields()["feature_dimension"].GetStringValue()
			sampleDimensionField, exists := responseData.Data.GetFields()["sample_dimension"]

			if exists {
				sampleDimension[client.Auth] = sampleDimensionField.GetListValue().GetValues()
			}

		}(weightIndex)
	}

	wg.Wait()

	orderedFeatureDimension := []any{}
	orderedSampleDimension := []any{}
	orderedActiveClients := []any{}

	for _, client := range clients {
		orderedFeatureDimension = append(orderedFeatureDimension, featureDimension[client.Auth])

		if sd, exists := sampleDimension[client.Auth]; exists {
			orderedSampleDimension = append(orderedSampleDimension, sd)
		}

		orderedActiveClients = append(orderedActiveClients, map[bool]int{true: 1, false: 0}[client.Active])
	}

	responseData, err = cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Authority,
		"vflMIFEDKGenerationRequest",
		map[string]any{
			"active_parties": orderedActiveClients,
		},
	)

	dkFeaturesMife := responseData.Data.GetFields()["dks_features_mife"].GetListValue().GetValues()

	responseData, err = cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Aggregator,
		"vflFeaturesDecryptionRequest",
		map[string]any{
			"dks_features_mife":            dkFeaturesMife,
			"encrypted_features_dimension": orderedFeatureDimension,
		},
	)

	if err != nil {
		return 0., 0., err
	}

	decryptedFeaturesDimension := responseData.Data.GetFields()["decrypted_features_dimension"].GetListValue().GetValues()

	responseData, err = cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Server,
		"vflCalculateAccuracyRequest",
		map[string]any{
			"decrypted_features_dimension": decryptedFeaturesDimension,
		},
	)

	if err != nil {
		return 0., 0., err
	}

	accuracy := responseData.Data.GetFields()["batch_accuracy"].GetNumberValue()
	loss := responseData.Data.GetFields()["batch_loss"].GetNumberValue()
	logisticError := responseData.Data.GetFields()["logistic_error"].GetListValue().GetValues()

	responseData, err = cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Authority,
		"vflSIFEDKGenerationRequest",
		map[string]any{
			"logistic_error": logisticError,
		},
	)

	if err != nil {
		return 0., 0., err
	}

	dkSamplesDimension := responseData.Data.GetFields()["dk_samples_sife"].GetStringValue()

	responseData, err = cloneAndSendDataRequest(dataRequest, authorizedProviders,
		Aggregator,
		"vflSamplesDecryptionRequest",
		map[string]any{
			"dk_samples_sife":             dkSamplesDimension,
			"encrypted_samples_dimension": orderedSampleDimension,
		},
	)

	*weights = ToAnyList(responseData.Data.GetFields()["weights"].GetListValue().GetValues())

	return accuracy, loss, nil
}

// #region VFL requests

// #endregion

func extractValueOrDefault[T ~int64 | ~float64](data map[string]any, propertyName string, defaultValue T) T {
	value, ok := data[propertyName].(float64)
	if ok {
		return T(value)
	}

	logger.Sugar().Debug("Property [", propertyName, "] wasn't found on the request parameters. Default value [", defaultValue, "] is going to be used instead.")
	return defaultValue
}

func checkPolicyUpdate(clients *[]ClientData, user *pb.User, policyChanged *bool) {
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

			if err != nil {
				logger.Sugar().Errorf("A problem occurred while fetching providers GetAvailableProviders: ", err)
			}

			validDataproviders := policyUpdateResponse.GetValidDataproviders()

			logger.Sugar().Debug("Clients before policy update: ", clients)

			clientsMutex.Lock()
			existingClients := make(map[string]bool)

			for i, client := range *clients {
				existingClients[client.Auth] = true

				_, isValid := validDataproviders[client.Auth]

				if isValid {
					// Policy reintroduced
					if !client.Active {
						(*clients)[i].Active = true
						logger.Sugar().Debug("[", client.Auth, "] [>!<PolicyChange>!<] Policy reintroduced.")
					}
				} else {
					// Policy removed
					if client.Active {
						(*clients)[i].Active = false
						logger.Sugar().Debug("[", client.Auth, "] [>!<PolicyChange>!<] Policy removed.")
					}
				}
			}

			for auth, agentDetail := range availableProviders {
				if shouldExcludeClient(strings.ToLower(auth)) {
					continue
				}

				_, isValid := validDataproviders[auth]

				if isValid && !existingClients[auth] {
					*clients = append(*clients, ClientData{
						Auth:   auth,
						Url:    agentDetail.Dns,
						Active: true,
					})
					*policyChanged = true
					logger.Sugar().Debug("[", auth, "] [>!<PolicyChange>!<] Policy added.")
				}
			}

			clientsMutex.Unlock()
			logger.Sugar().Debug("Clients after policy update: ", clients)
		}

		policyUpdateMutex.Lock()
		delete(policyUpdateMap, user.Id)
		policyUpdateMutex.Unlock()
	}()
}

type ClientData struct {
	Auth   string
	Url    string
	Active bool
}

func shouldExcludeClient(auth string) bool {
	return slices.Contains(excludedClients, auth)
}

func runVFLTraining(dataRequest map[string]any, authorizedProviders map[string]string, jobId string, ctx context.Context, requestID string) []byte {
	clients := &[]ClientData{}
	var policyChanged bool
	var finalAccuracy float64
	var wg sync.WaitGroup
	var weights = []any{}
	var nonImprovementCounter int64
	var bestLoss float64

	// Default parameters values
	var sampleBatchSize int64 = 64
	var cycles int64 = 10
	var patience int64 = 10
	var learningRate float64 = 0.05
	var policy_removal int64 = -1
	var policy_reintroduction int64 = -1
	var dataProviders []string = []string{}

	var trainingBacktrack int64 = 0 // Default value

	data, ok := dataRequest["data"].(map[string]any)
	logger.Sugar().Info("Data from req: ", data)

	if ok {
		// Parameters extraction
		sampleBatchSize = extractValueOrDefault(data, "sample_batch_size", sampleBatchSize)
		cycles = extractValueOrDefault(data, "cycles", cycles)
		patience = extractValueOrDefault(data, "patience", patience)
		learningRate = extractValueOrDefault(data, "learning_rate", learningRate)
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

	trainingFailed := false

	for auth, url := range authorizedProviders {
		lower := strings.ToLower(auth)

		if !shouldExcludeClient(lower) && url != "" {
			*clients = append(*clients, ClientData{Auth: auth, Url: url, Active: true})
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
			for i := range 10 {
				logger.Sugar().Info("Sending ping to: ", target, " (", endpoint, "). Attempt [", i+1, "/10]")
				_, err := sendData(endpoint, dataRequestJson)

				if err == nil {
					logger.Sugar().Info("Response OK from: ", target)
					break
				}

				logger.Sugar().Info("No response from: ", target)

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
	checkPolicyUpdate(clients, user, &policyChanged)

	initializeVFLServices(dataRequest, getSafeClients(clients), &weights, authorizedProviders, sampleBatchSize)

	logger.Sugar().Info("Running VFL for ", cycles, " rounds")
	for cycle := range cycles {
		logger.Sugar().Info("Running VFL training round ", cycle)

		currentClients := getSafeClients(clients)

		if policyChanged {
			// Aggreement has been added. Re-initilization is mandatory.
			initializeVFLServices(dataRequest, currentClients, &weights, authorizedProviders, sampleBatchSize)
			policyChanged = false
		}

		// TODO: Implement policy change request
		if policy_removal == cycle {
			logger.Sugar().Info("Sending in the policy change request, removing client 3 from the agreement.")
			logger.Sugar().Info("TODO: Policy change request not yet implemented.")

			api.DeleteRequest(
				"http://orchestrator.orchestrator.svc.cluster.local:8080/api/v1/policyEnforcer/agreements/clientthree",
				"",
				nil)
		}

		// TODO: Implement policy change request
		if policy_reintroduction == cycle {
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

		accuracy, loss, err := runVFLTrainingRound(dataRequest, currentClients, &weights, authorizedProviders, sampleBatchSize)

		finalAccuracy = accuracy

		if err != nil {
			logger.Sugar().Error("Training round returned an error.")
			trainingFailed = true
			break
		}

		activeClientsCount := 0

		for _, client := range currentClients {
			if client.Active {
				activeClientsCount++
			}
		}

		addAndUpdateTrainingRequest(requestID, cycle, activeClientsCount, accuracy)

		if cycle == 0 {
			bestLoss = loss
		} else {
			if bestLoss <= loss {
				nonImprovementCounter++
			} else {
				nonImprovementCounter = 0
				bestLoss = loss
			}
		}

		if trainingFailed || (cycle+1 >= patience && nonImprovementCounter == patience) {
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

	results, _ := getTrainingRequest(requestID)

	new_response := map[string]any{
		"metadata": metadata,
		"results":  results.Results,
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
