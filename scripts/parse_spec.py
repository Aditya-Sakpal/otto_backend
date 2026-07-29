import json

spec = json.load(open('D:/ottoai/backend/scripts/shunya_spec.json'))
paths = spec.get('paths', {})

for path, methods in paths.items():
    if 'tenant' in path or 'sop' in path:
        for method, details in methods.items():
            if method in ['get','post','put','patch']:
                print(f'\n=== {method.upper()} {path} ===')
                body = details.get('requestBody', {})
                if body:
                    content = body.get('content', {})
                    for ct, schema_info in content.items():
                        schema = schema_info.get('schema', {})
                        ref = schema.get('$ref', '')
                        if ref:
                            model_name = ref.split('/')[-1]
                            model = spec.get('components', {}).get('schemas', {}).get(model_name, {})
                            print(f'  Body ({ct}): {model_name}')
                            props = model.get('properties', {})
                            for k, v in props.items():
                                vtype = v.get('type', v.get('$ref','').split('/')[-1] if '$ref' in v else '?')
                                print(f'    {k}: {vtype} -- {v}')
                            print(f'  Required: {model.get("required", [])}')
