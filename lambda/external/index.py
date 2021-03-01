import json
import os

import boto3

EXTENSION_TO_CONTENT_TYPE_MAP = {
    'js': 'text/javascript',
    'css': 'text/css',
    'yml': 'text/yaml',
    'html': 'text/html'
}


def handler(event, context):
    split_path = event['path'].split('/')
    first_path_part = split_path[1]  # Yes, 1 - the 0th element is `''`
    if first_path_part == 'api':
        if len(split_path) == 2 or (len(split_path) == 3 and split_path[2] == ''):
            # i.e. if path was simply `/api` or `/api/`
            return {
                'statusCode': 200,
                # TODO - maybe print the available methods?
                'body': 'Call the path /api/<method>'
            }

        event['path'] = '/' + '/'.join(split_path[2:])

        responseBody = boto3.client('lambda').invoke(
            FunctionName=os.environ['apiFunctionArn'],
            Payload=json.dumps(event))
        return {
            'statusCode': responseBody['StatusCode'],
            'body': responseBody['Payload'].read().decode('utf-8'),
            'headers': {
                # RIP
                'X-Clacks-Overhead': 'GNU Terry Pratchett',
                'Content-Type': 'application/json'
            }
        }

    else:  # That is - this was not an API request
        key = event['path'][1:]

        # Translate an extension-less path to `.html`, and moreover the empty path to `index.html`
        # TODO: This will probably need some more attention if we start providing any other types
        # of file than just .html, .css, and .js
        if key == '':
            key = 'index'
        if not any([key.endswith('.'+ext) for ext in EXTENSION_TO_CONTENT_TYPE_MAP]):
            key = key+'.html'

        print(f'Retrieving static content for {key}')
        obj = boto3.resource('s3') \
            .Object(os.environ["staticSiteBucket"], key)
        return {
            'statusCode': 200,
            'body': obj.get()['Body'].read().decode('utf-8'),
            'headers': {
                'Content-Type': _get_content_type_from_key(event['path'][1:])
            }
        }


def _get_content_type_from_key(key):
    # Default to text/html because we want to be able to reference html files as
    return EXTENSION_TO_CONTENT_TYPE_MAP.get(key.split('.')[-1], 'text/html')
