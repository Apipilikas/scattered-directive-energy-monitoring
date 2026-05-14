import pandas as pd
import numpy as np
import sys
import os
import io
import json
import torch
import torch.nn as nn
import torch.optim as optim
from collections import OrderedDict
from sklearn.preprocessing import StandardScaler
from google.protobuf.struct_pb2 import Struct, ListValue, Value
import argparse

def filter_data(rows, columns, filter_columns):
    return [d for i, d in enumerate(rows) if columns[i] in filter_columns]


def bin_age(age_series):
    bins = [-np.inf, 18, 60, np.inf]
    labels = ["Child", "Adult", "Elderly"]
    return (
        pd.cut(age_series, bins=bins, labels=labels, right=True)
        .astype(str)
        .replace("nan", "Unknown")
    )


def _extract_title(name_series):
    titles = name_series.str.extract(" ([A-Za-z]+)\\.", expand=False)
    rare_titles = {
        "Lady",
        "Countess",
        "Capt",
        "Col",
        "Don",
        "Dr",
        "Major",
        "Rev",
        "Sir",
        "Jonkheer",
        "Dona",
    }
    titles = titles.replace(list(rare_titles), "Rare")
    titles = titles.replace({"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"})
    return titles


def _create_features(df):
    # Convert 'Age' to numeric, coercing errors to NaN
    df["Age"] = pd.to_numeric(df["Age"], errors="coerce")
    df["Age"] = bin_age(df["Age"])
    df["Cabin"] = df["Cabin"].str[0].fillna("Unknown")
    df["Title"] = _extract_title(df["Name"])
    df.drop(columns=["Name", "Ticket"], inplace=True)
    # keywords = set(df.columns)
    # print(all_keywords)
    df = pd.get_dummies(
        df, columns=["Sex", "Pclass", "Embarked", "Title", "Cabin", "Age"]
    )
    df["Cabin_T"] = False
    return df
    

def main():
    test = _resolve_args()
    file_name = "csv_splitter_configuration.json"

    if test:
        file_name = "csv_splitter_test_configuration.json"

    with open(file_name, 'r') as file:
        configuration = json.load(file)

    df = pd.read_csv(configuration["file"])
    # processed_df = df.dropna(subset=["Embarked", "Fare"]).copy()
    data = _create_features(df)

    for partition in configuration["partitions"]:
        os.makedirs(partition["outputDirectory"], exist_ok=True)
        print(partition["columns"])
        partition_data = data[list({
            column
            for column in data.columns
            for keyword in partition["columns"]
            if keyword in column
        })]

        partition_data.to_csv(
            partition["outputDirectory"] + partition["name"] + ".csv")

def _resolve_args():
    parser = argparse.ArgumentParser()
    
    parser.add_argument("-t", "--test", action="store_true")

    args = parser.parse_args()
    test_arg = args.test

    return test_arg

if __name__ == "__main__":
    main()