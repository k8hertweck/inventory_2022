"""
Purpose: Preprocess and tokenize data, create DataLoader
Authors: Ana-Maria Istrate and Kenneth Schackart
"""

import random
import re
import sys
from functools import partial
from typing import List, NamedTuple, Optional, TextIO, Tuple

import pandas as pd
from datasets import ClassLabel, Dataset
from pandas.testing import assert_frame_equal
from torch.utils.data import DataLoader
from transformers import AutoTokenizer


# ---------------------------------------------------------------------------
class DataFields(NamedTuple):
    """ Fields in data used for training and classification """
    predictive: str  # Column used for prediction
    labels: Optional[str]  # Column containing labels
    descriptive_labels: List[str]  # Description of labels


# ---------------------------------------------------------------------------
class RunParams(NamedTuple):
    """ Model and run parameters """
    model_name: str  # Huggingface model name
    batch_size: int  # Tokenization batch size
    max_len: int  # Tokenization max length
    num_train: Optional[int]  # Number of training datapoints


# ---------------------------------------------------------------------------
def get_dataloader(file: TextIO, fields: DataFields,
                   run_params: RunParams) -> DataLoader:
    """ Preprocess data and create dataloader """

    df = preprocess_data(file)

    data_loader = generate_dataloader(df, file.name, fields, run_params)

    return data_loader


# ---------------------------------------------------------------------------
def preprocess_data(file: TextIO) -> pd.DataFrame:
    """ Strip XML tags and concatenate title and abstract columns """

    df = pd.read_csv(file)

    if not all(map(lambda c: c in df.columns, ['title', 'abstract'])):
        sys.exit(f'Data file {file.name} must contain columns '
                 'labeled "title" and "abstract".')

    for col in ['title', 'abstract']:
        df[col] = df[col].apply(lambda s: strip_xml(s))

    df = concat_title_abstract(df)

    return df


# ---------------------------------------------------------------------------
def test_preprocess_data() -> None:
    """ Test preprocess_data() """

    pass


# ---------------------------------------------------------------------------
def strip_xml(text: str) -> str:
    """ Strip XML tags from a text string """

    return re.sub(r'<[\w/]+>', '', text)


# ---------------------------------------------------------------------------
def test_strip_xml() -> None:
    """ Test strip_xml() """

    assert strip_xml('<h4>Supplementary info</h4>') == 'Supplementary info'
    assert strip_xml('H<sub>2</sub>O<sub>2</sub>') == 'H2O2'
    assert strip_xml(
        'the <i>Bacillus pumilus</i> group.') == 'the Bacillus pumilus group.'


# ---------------------------------------------------------------------------
def concat_title_abstract(df: pd.DataFrame) -> pd.DataFrame:
    """ Concatenate abstract and title columns """

    df['title_abstract'] = df['title'] + ' - ' + df['abstract']

    return df


# ---------------------------------------------------------------------------
def test_concat_title_abstract() -> None:
    """ Test concat_title_abstract() """

    in_df = pd.DataFrame([['A Descriptive Title', 'A detailed abstract.']],
                         columns=['title', 'abstract'])

    out_df = pd.DataFrame([[
        'A Descriptive Title', 'A detailed abstract.',
        'A Descriptive Title - A detailed abstract.'
    ]],
                          columns=['title', 'abstract', 'title_abstract'])

    assert_frame_equal(concat_title_abstract(in_df), out_df)


# ---------------------------------------------------------------------------
def generate_dataloader(df: pd.DataFrame, filename: str, fields: DataFields,
                        params: RunParams) -> DataLoader:
    """ Generate dataloader from preprocessed data """

    if fields.predictive not in df.columns:
        sys.exit(f'Predictive field column "{fields.predictive}" '
                 f'not in file {filename}.')

    if fields.labels and fields.labels not in df.columns:
        sys.exit(f'Labels field column "{fields.labels}" '
                 f'not in file {filename}.')

    text, labels = get_text_labels(df, fields)

    class_labels = ClassLabel(num_classes=2, names=fields.descriptive_labels)

    tokenizer = AutoTokenizer.from_pretrained(params.model_name)

    dataset = tokenize_text(text, labels, class_labels, tokenizer,
                            params.max_len)

    if params.num_train:
        dataset = dataset.select(
            random.sample(range(dataset.num_rows), k=params.num_train))

    return DataLoader(dataset, batch_size=params.batch_size)


# ---------------------------------------------------------------------------
def get_text_labels(df: pd.DataFrame, fields: DataFields) -> Tuple[List, List]:
    """ Get lists of predictive text and (optionally) labels """

    text = df[fields.predictive].tolist()

    labels = []
    if fields.labels:
        labels = df[fields.labels].tolist()

    return text, labels


# ---------------------------------------------------------------------------
def test_get_text_labels() -> None:
    """ Test get_text_labels() """

    df = pd.DataFrame(
        [['Title 1', 'Abstract 1', 0], ['Title 2', 'Abstract 2', 1],
         ['Title 3', 'Abstract 3', 0]],
        columns=['title', 'abstract', 'score'])

    fields = DataFields('title', None, ['yes', 'no'])

    assert get_text_labels(df, fields) == (['Title 1', 'Title 2',
                                            'Title 3'], [])

    fields = DataFields('title', 'score', ['yes', 'no'])

    assert get_text_labels(df, fields) == (['Title 1', 'Title 2',
                                            'Title 3'], [0, 1, 0])


# ---------------------------------------------------------------------------
def tokenize_text(text: List, labels: List, class_labels: ClassLabel,
                  tokenizer: AutoTokenizer, max_len: int) -> Dataset:
    """ Tokenize predictive text """

    data = {'text': text}
    if labels:
        data['labels'] = labels
    dataset = Dataset.from_dict(data)

    # Partially apply arguments to the tokenizer so it is ready to tokenize
    tokenize = partial(tokenizer,
                       padding='max_length',
                       max_length=max_len,
                       truncation=True)

    tokenized_dataset = dataset.map(lambda x: tokenize(x['text']),
                                    batched=True)

    if labels:
        tokenized_dataset = tokenized_dataset.cast_column(
            'labels', class_labels)

    tokenized_dataset = tokenized_dataset.remove_columns(['text'])
    tokenized_dataset.set_format("torch")

    return tokenized_dataset
