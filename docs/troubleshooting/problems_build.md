## Problem while running makefile
```
make api-gateway
go mod tidy                                                                                                                                                     
go: errors parsing go.mod:
/mnt/c/Users/apipi/Documents/UNI/master/MP/scattered-directive-energy-monitoring/go/go.mod:5: unknown directive: toolchain
make: *** [Makefile:6: prepare] Error 1
```

The problem here was that the installed go version was old (13.1). I had to download a newer one.
```
sudo apt remove golang-go -y
sudo apt autoremove -y
wget https://go.dev/dl/go1.26.1.linux-amd64.tar.gz
sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.26.1.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin
```

## Protoc not found
```
sudo apt update && sudo apt install protobuf-compiler -y
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
export PATH="$PATH:$(go env GOPATH)/bin"
```

## Images were not deployed in pods
This was because files pulled image from dynamos1 repository. Also, as we don't have permissions to push images, I changed the configuration in order to look up on my docker account. Simpler alternative would be the following:
```yaml
image:
  repository: dynamos1/api-gateway
  tag: "latest"
  pullPolicy: IfNotPresent
```