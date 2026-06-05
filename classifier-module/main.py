from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
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

    df = pd.read_csv(io.BytesIO(input), sep=None, engine='python')
    output = process_csv(df, use_ollama)

    output_df = pd.DataFrame(output)
    csv_string = output_df.to_csv(index=False, sep=';')

    return Response(
        content=csv_string,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=processed_{file.filename}"}
    )