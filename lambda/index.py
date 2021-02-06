import json

def handler(event, context):
    print(f'request: {json.dumps(event)}')
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/plain',
            'X-Clacks-Overhead': 'GNU Terry Pratchett'
        },
        'body': f'Hello! You have hit the path {event["path"]}!'
    }
