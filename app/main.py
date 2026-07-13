import io
import os
import tempfile

import numpy as np
import pandas as pd
from enum import Enum
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import Response, JSONResponse

from .config import log, DEFAULT_CONFIG
from .llm_lookup import classify_land
from .pipeline import process_csv
from .util.models import LLMMatch, TextRequest, TestModels, ClassifyCSVRequest

app = FastAPI(
    title='Land Taxonomy Classifier and Plant Taxonomy Service',
    version='1.0.0',
)

@app.get('/')
def root():
    return {'status': 'ok'}

'''
@app.post('/classify', response_model=CLCMatch)
async def classify_text(req: TextRequest) -> CLCMatch:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail='text must not be empty')
    return await classify_land(req.text)
    
@app.post('/test-models', response_model=list[TestModels])
async def test_multiple_models(req: TextRequest) -> list[TestModels]:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail='text must not be empty')

    output = []
    models = req.models
    reps = req.reps

    for model in models:
        rows = []
        for rep in range(reps):
            r = await classify_land(req.text, req.use_ollama, model)
            rows.append(r)
        output.append({
            'model': model,
            'cost': -1,
            'prob_code': 'TODO',
            'output': rows,
        })
    
    return output
'''

class OutputFormat(str, Enum):
    csv = 'csv'
    json = 'json'

@app.post('/classify/csv')
async def classify_csv(
    file: UploadFile = File(...),
    fmt: OutputFormat = Query(default=OutputFormat.csv, description='Response format.'),
):
    # log.info(req)
    if not file.filename or not file.filename.endswith('.csv'):
        log.warning('Rejected upload: not a CSV (filename=%s)', file.filename)
        raise HTTPException(status_code=400, detail='Only CSV files are supported.')

    content = await file.read()
    df = pd.read_csv(io.BytesIO(content), sep=None, engine='python')
    log.info('Received %s with %d rows (use_ollama=)', file.filename, len(df)) #use_ollama)


    # process_csv writes to temp file
    result = await process_csv(
        df=df,
        model=DEFAULT_CONFIG['model'],
        version=DEFAULT_CONFIG['version'],
    )

    if fmt is OutputFormat.json:
        return JSONResponse(content={
            'rows': len(result),
            'columns': list(result.columns),
            'data': result.replace({np.nan: None}).to_dict(orient='records'),
        })

    return Response(
        content=result.to_csv(index=False),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=processed_{file.filename}'},
    )