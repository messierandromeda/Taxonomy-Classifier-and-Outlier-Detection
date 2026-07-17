import io

import numpy as np
import pandas as pd
from enum import Enum
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import Response, JSONResponse
import json

from .config import log, DEFAULT_CONFIG
from .pipeline import process_csv

app = FastAPI(
    title='Land Taxonomy Classifier and Plant Taxonomy Service',
    version='1.0.0',
)

@app.get('/')
def root():
    return {'status': 'ok'}

class OutputFormat(str, Enum):
    csv = 'csv'
    json = 'json'

@app.post('/classify')
async def classify(
    file: UploadFile = File(...),
    fmt: OutputFormat = Query(default=OutputFormat.csv, description='Response format.'),
    download_file: bool = True,
):

    if not file.filename or not file.filename.endswith(('.csv', '.json')):
        log.warning('Rejected upload: not a CSV or JSON (filename=%s)', file.filename)
        raise HTTPException(status_code=400, detail='Only CSV or JSON files are supported.')

    content = await file.read()
    if fmt is OutputFormat.json:
        df = pd.read_json(io.BytesIO(content))
    else:
        df = pd.read_csv(io.BytesIO(content), sep=None, engine='python')
    
    log.info('Received %s with %d rows', file.filename, len(df))


    # process_csv writes to temp file
    result = await process_csv(
        df=df,
        model=DEFAULT_CONFIG['model'],
        version=DEFAULT_CONFIG['version'],
    )

    if fmt is OutputFormat.json:
        if download_file:
            payload = {
                'rows': len(result),
                'columns': list(result.columns),
                'data': result.replace({np.nan: None}).to_dict(orient='records'),
            }

            json_bytes = json.dumps(payload).encode('utf-8')
    
            return Response(
                content=json_bytes,
                media_type='application/json',
                headers={'Content-Disposition': f'attachment; filename=processed_{file.filename}'},
            )
        else:
            return JSONResponse(content={
                'rows': len(result),
                'columns': list(result.columns),
                'data': result.replace({np.nan: None}).to_dict(orient='records'),
            })

    if download_file:
        return Response(
            content=result.to_csv(index=False),
            media_type='text/csv',
            headers={'Content-Disposition': f'attachment; filename=processed_{file.filename}'},
        )
    
    else: 
        return result.to_dict(orient='records')