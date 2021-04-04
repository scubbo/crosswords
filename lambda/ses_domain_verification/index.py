import json
import uuid

import boto3
import requests


def handler(event, context):
    print("Received event: ")
    print(event)

    resource_type = event['ResourceType']
    request_type = event['RequestType']
    resource_properties = event['ResourceProperties']
    hosted_zone_id = resource_properties['HostedZoneId']

    physical_resource_id = event.get('PhysicalResourceId', uuid.uuid4())

    response_data = None

    try:
        if resource_type == "Custom::AmazonSesVerificationRecords":
            if request_type == 'Create':
                verify_ses(hosted_zone_id=hosted_zone_id, action='UPSERT')
            elif request_type == 'Delete':
                verify_ses(hosted_zone_id=hosted_zone_id, action='DELETE')
            elif request_type == 'Update':
                old_hosted_zone_id = event['OldResourceProperties']['HostedZoneId']
                verify_ses(hosted_zone_id=old_hosted_zone_id, action='DELETE')
                verify_ses(hosted_zone_id=hosted_zone_id, action='UPSERT')
            else:
                print(f'Request type is {request_type}, doing nothing.')
                response_data = {}
        else:
            raise ValueError(f"Unexpected resource_type: {resource_type}")
    except Exception:
        send(
            event,
            context,
            responseStatus='FAILED' if request_type != 'Delete' else 'SUCCESS',
            # Do not fail on delete to avoid rollback failure
            responseData=None,
            physicalResourceId=physical_resource_id,
        )
        # This statement is important so the exception (along with the original traceback)
        # is logged to Cloudwatch
        raise
    else:
        send(
            event,
            context,
            responseStatus='SUCCESS',
            responseData=response_data,
            physicalResourceId=physical_resource_id,
        )


def verify_ses(hosted_zone_id, action):
    ses = boto3.client('ses')
    print("Retrieving Hosted Zone name")
    hosted_zone_name = _get_hosted_zone_name(hosted_zone_id=hosted_zone_id)
    print(f'Hosted zone name: {hosted_zone_name}')

    domain = hosted_zone_name.rstrip('.')

    verification_token = ses.verify_domain_identity(
        Domain=domain
    )['VerificationToken']

    dkim_tokens = ses.verify_domain_dkim(
        Domain=domain
    )['DkimTokens']

    print('Changing resource record sets')
    changes = [
        {
            'Action': action,
            'ResourceRecordSet': {
                'Name': f"_amazonses.{hosted_zone_name}",
                'Type': 'TXT',
                'TTL': 1800,
                'ResourceRecords': [
                    {
                        'Value': f'"{verification_token}"'
                    }
                ]
            }
        }
    ]

    for dkim_token in dkim_tokens:
        change = {
            'Action': action,
            'ResourceRecordSet': {
                'Name': f"{dkim_token}._domainkey.{hosted_zone_name}",
                'Type': 'CNAME',
                'TTL': 1800,
                'ResourceRecords': [
                    {
                        'Value': f"{dkim_token}.dkim.amazonses.com"
                    }
                ]
            }
        }

        changes.append(change)

        boto3.client('route53').change_resource_record_sets(
            ChangeBatch={
                'Changes': changes
            },
            HostedZoneId=hosted_zone_id
        )


def _get_hosted_zone_name(hosted_zone_id):
    route53 = boto3.client('route53')
    route53_resp = route53.get_hosted_zone(
        Id=hosted_zone_id
    )
    return route53_resp['HostedZone']['Name']


def send(event, context, responseStatus, responseData, physicalResourceId):
    responseUrl = event['ResponseURL']

    print(responseUrl)

    responseBody = {}
    responseBody['Status'] = responseStatus
    responseBody['Reason'] = 'See the details in CloudWatch Log Stream: ' + context.log_stream_name
    responseBody['PhysicalResourceId'] = physicalResourceId
    responseBody['StackId'] = event['StackId']
    responseBody['RequestId'] = event['RequestId']
    responseBody['LogicalResourceId'] = event['LogicalResourceId']
    responseBody['Data'] = responseData

    json_responseBody = json.dumps(responseBody)

    print("Response body:\n" + json_responseBody)

    headers = {
        'content-type': '',
        'content-length': str(len(json_responseBody))
    }

    try:
        response = requests.put(responseUrl,
                                data=json_responseBody,
                                headers=headers)
        print("Status code: " + response.reason)
    except Exception as e:
        print("send(..) failed executing requests.put(..): " + str(e))
