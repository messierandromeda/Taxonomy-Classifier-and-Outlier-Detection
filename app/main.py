import io
import os
import tempfile

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import Response

from config import log
from land_classifier import classify_land
from pipeline import process_csv
from models import CLCMatch, TextRequest, TestModels

app = FastAPI(
    title='Land Taxonomy Classifier and Plant Taxonomy Service',
    version='1.0.0',
)

@app.get('/')
def root():
    return {'status': 'ok'}


@app.post('/classify', response_model=CLCMatch)
async def classify_text(req: TextRequest) -> CLCMatch:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail='text must not be empty')
    return await classify_land(req.text, req.use_ollama)
    
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

@app.post('/classify/csv')
async def classify_csv(
    file: UploadFile = File(...),
    use_ollama: bool = Query(default=False, description='Use Ollama instead of OpenAI.'),
):
    if not file.filename or not file.filename.endswith('.csv'):
        log.warning('Rejected upload: not a CSV (filename=%s)', file.filename)
        raise HTTPException(status_code=400, detail='Only CSV files are supported.')

    content = await file.read()
    df = pd.read_csv(io.BytesIO(content), sep=None, engine='python')
    log.info('Received %s with %d rows (use_ollama=%s)', file.filename, len(df), use_ollama)

    # process_csv writes to temp file
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
        output_path = tmp.name
    try:
        await process_csv(df, use_ollama, output_path=output_path)
        with open(output_path, 'r') as f:
            csv_string = f.read()
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

    return Response(
        content=csv_string,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=processed_{file.filename}'},
    )