import os
import time
from dotenv import load_dotenv

load_dotenv()

import easyocr
from google import genai
from src.classifier import classify_dataset

print("Loading OCR Model and LLM Client...", flush=True)
ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
llm_client = genai.Client()

print("\nRunning classification on ./test_images...", flush=True)
start_time = time.time()

results = classify_dataset(
    dataset_dir="./test_images",
    ocr_reader=ocr_reader,
    llm_client=llm_client
)

print(f"{'Filename':<15} | {'Doc Type':<15} | {'Sub Type':<20} | {'Method':<8} | {'Latency (ms)':<10}")
print("-" * 75)
for r in results:
    sub = r.sub_type if r.sub_type else "None"
    print(f"{r.filename:<15} | {r.doc_type:<15} | {sub:<20} | {r.method:<8} | {r.latency_ms:<10}")

print(f"\nTotal time: {time.time() - start_time:.2f}s")
