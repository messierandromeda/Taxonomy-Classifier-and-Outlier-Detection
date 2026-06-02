from fastapi import FastAPI, HTTPException, UploadFile, File, Query
import pandas as pd
import io
from pipeline import process_csv

app = FastAPI(
    title='Land Taxonomy Classifier and Plant Taxonomy Service',
)

@app.get('/')
def root():
    return {'status': 'ok'}

@app.post('/classify')
async def classify_csv(
    file: UploadFile = File(...),
    use_ollama: bool = Query(default=False, title='Use Ollama', description='Choose if there`s no OpenAI API key.')
    ):
    input = await file.read()

    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail='Only CSV files are supported.')

    df = pd.read_csv(io.BytesIO(input))
    process_csv(df, use_ollama)



