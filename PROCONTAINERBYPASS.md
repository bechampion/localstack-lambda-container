# ByPass pro checks for container based lambdas

## 1 Create your simple image to run in a lambda

```Dockerfile
FROM public.ecr.aws/lambda/python:3.9

COPY lambda_function.py ${LAMBDA_TASK_ROOT}

CMD ["lambda_function.lambda_handler"]
```

*lambda_function.py* looks like this

```python
import json

def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Hello from Docker container!',
            'event': event
        })
    }
```

### Build and run the image for localstack 

```bash
make docker-build
...

❯ docker run --rm -e DEBUG=1 -e LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=600 -e SERVICES=lambda,ecr -v /var/run/docker.sock:/var/run/docker.sock -it -p 4566:4566 docker.io/localstack/localstack
LocalStack supervisor: starting
LocalStack supervisor: localstack process (PID 13) starting
2025-09-05T08:57:23.867 DEBUG --- [  MainThread] l.utils.docker_utils       : Using SdkDockerClient. LEGACY_DOCKER_CLIENT: False, SDK installed: True
2025-09-05T08:57:23.965  WARN --- [  MainThread] l.services.internal        : Enabling diagnose endpoint, please be aware that this can expose sensitive information via your network.
2025-09-05T08:57:23.969 DEBUG --- [  MainThread] plux.runtime.manager       : instantiating plugin PluginSpec(localstack.runtime.components.aws = <class 'localstack.aws.components.AwsComponents'>)
2025-09-05T08:57:23.969 DEBUG --- [  MainThread] plux.runtime.manager       : loading plugin localstack.runtime.components:aws

LocalStack version: 4.7.1.dev127

```

## Build your image , tag and deploy your lambdas

```bash
#!/bin/bash
docker build . 
docker tag lambda:latest docker.io/bechampion/lambda:latest
docker push docker.io/bechampion/lambda:latest


aws --endpoint-url=http://localhost:4566 lambda create-function \
  --function-name my-container-lambda \
  --role arn:aws:iam::123456789012:role/lambda-role \
  --code ImageUri=docker.io/bechampion/lambda:latest \
  --package-type Image

aws --endpoint-url=http://localhost:4566 lambda invoke \
  --function-name my-container-lambda \
  --payload '{"test": "hello"}' \
  response.json

cat response.json
```

The output should be something like this

```bash
~/Projects/disney/lambdadocker
❯ bash deploy.sh
{
    "FunctionName": "my-container-lambda",
    "FunctionArn": "arn:aws:lambda:us-east-1:000000000000:function:my-container-lambda",
    "Role": "arn:aws:iam::123456789012:role/lambda-role",
    "CodeSize": 0,
    "Description": "",
    "Timeout": 3,
    "MemorySize": 128,
    "LastModified": "2025-09-05T09:00:40.533079+0000",
    "CodeSha256": "edf03542d51b2c39026d2a879ab0e426067a50ad9103627b403c0d75f9eed853",
    "Version": "$LATEST",
    "TracingConfig": {
        "Mode": "PassThrough"
    },
    "RevisionId": "de498fa1-5b64-45de-9923-43b362b2ef30",
    "State": "Pending",
    "StateReason": "The function is being created.",
    "StateReasonCode": "Creating",
    "PackageType": "Image",
    "Architectures": [
        "x86_64"
    ],
    "EphemeralStorage": {
        "Size": 512
    },
    "SnapStart": {
        "ApplyOn": "None",
        "OptimizationStatus": "Off"
    },
    "LoggingConfig": {
        "LogFormat": "Text",
        "LogGroup": "/aws/lambda/my-container-lambda"
    }
}
{
    "StatusCode": 200,
    "ExecutedVersion": "$LATEST"
}
{"statusCode": 200, "body": "{\"message\": \"Hello from Docker container!\", \"event\": {\"test\": \"hello\"}}"}

~/Projects/disney/lambdadocker
❯ docker ps
CONTAINER ID   IMAGE                      COMMAND                  CREATED         STATUS                   PORTS                                                                  NAMES
7cdd114fd219   bechampion/lambda:latest   "/lambda-entrypoint.…"   7 seconds ago   Up 6 seconds                                                                                    youthful-brattain-lambda-my-container-lambda-01edbe15386f0fd15cc5ca46c6a93a14
6d57a75532f6   localstack/localstack      "docker-entrypoint.sh"   3 minutes ago   Up 3 minutes (healthy)   4510-4559/tcp, 5678/tcp, 0.0.0.0:4566->4566/tcp, [::]:4566->4566/tcp   youthful_brattainA
```

See the lambda running as a container



