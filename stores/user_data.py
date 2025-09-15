import os
import threading

import pandas as pd

_docs_lock = threading.Lock()


def retrieve_user_data():
    bucket: str = os.getenv("BUCKET_NAME")
    key = os.getenv("BUCKET_USER_KEY")

    with _docs_lock:
        df = pd.read_csv(f"s3://{bucket}/{key}")
        return df

user_df = retrieve_user_data()
