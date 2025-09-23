import os
import threading

import pandas as pd

_docs_lock = threading.Lock()


def retrieve_user_data():
    bucket: str = os.getenv("BUCKET_NAME")
    key = os.getenv("BUCKET_USER_KEY")
    key_user_name = os.getenv("USER_TEST_NAME")

    with _docs_lock:
        df = pd.read_csv(f"s3://{bucket}/{key}")
        #df = pd.read_csv("data/Connections.csv")
        df1 = df[(df["First Name"] == key_user_name)]
        values = df1['Values'].iloc[0]
        print(f"values is {values}")
        return df

user_df = retrieve_user_data()
