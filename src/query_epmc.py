#!/usr/bin/env python3
"""
Purpose: Run query on EuropePMC
Authors: Ana Maria Istrate and Kenneth Schackart
"""

import argparse
import os
import re
from datetime import datetime
from typing import NamedTuple, Tuple, cast

import pandas as pd
import requests

from utils import CustomHelpFormatter


# ---------------------------------------------------------------------------
class Args(NamedTuple):
    """ Command-line arguments """
    query: str
    last_date: str
    out_dir: str


# ---------------------------------------------------------------------------
def get_args() -> Args:
    """ Parse command-line arguments """

    parser = argparse.ArgumentParser(
        description=('Query EuropePMC to retrieve articles. '
                     'Saves csv of results and file of today\'s date'),
        formatter_class=CustomHelpFormatter)

    parser.add_argument('query',
                        metavar='QUERY',
                        type=str,
                        help='EuropePMC query to run (file or string)')
    parser.add_argument('-d',
                        '--date',
                        metavar='DATE',
                        type=str,
                        default='2011',
                        help='Date of last run YYYY-MM-DD (file or string)')
    parser.add_argument('-o',
                        '--out-dir',
                        metavar='DIR',
                        type=str,
                        default='out/',
                        help='Output directory')

    args = parser.parse_args()

    if os.path.isfile(args.query):
        args.query = open(args.query).read()
    if os.path.isfile(args.date):
        args.date = open(args.date).read()

    date_pattern = re.compile(
        r'''^           # Beginning of date string
            [\d]{4}     # Must start wwith 4 digit year
            (-[\d]{2}   # Optionally 2 digit month
            (-[\d]{2})? # Optionally 2 digit day
            )?          # Finish making month optional
            $           # Followed by nothing else
            ''', re.X)
    if not re.match(date_pattern, args.date):
        parser.error(f'Last date "{args.date}" must be one of:\n'
                     '\t\t\tYYYY\n'
                     '\t\t\tYYYY-MM\n'
                     '\t\t\tYYYY-MM-DD')

    return Args(args.query, args.date, args.out_dir)


# ---------------------------------------------------------------------------
def make_filenames(outdir: str) -> Tuple[str, str]:
    '''
    Make filenames for output csv file and last date text file
    
    Parameters:
    `outdir`: Output directory
    
    Return: Tuple of csv and txt filenames
    '''

    csv_out = os.path.join(outdir, 'new_query_results.csv')
    txt_out = os.path.join(outdir, 'last_query_date.txt')

    return csv_out, txt_out


# ---------------------------------------------------------------------------
def test_make_filenames() -> None:
    """ Test make_filenames() """

    assert make_filenames('data/new_query') == (
        'data/new_query/new_query.csv', 'data/new_query/last_query_date.txt')


# ---------------------------------------------------------------------------
def clean_results(results: dict) -> pd.DataFrame:
    """
    Retrieve the PMIDs, titles, and abstracts from results of query
    
    Parameters:
    `results`: JSON-encoded response (nested dictionary)
    
    Return: Dataframe of results
    """

    pmids = []
    titles = []
    abstracts = []
    for paper in results.get('resultList').get('result'):
        pmids.append(paper.get('pmid'))
        titles.append(paper.get('title'))
        abstracts.append(paper.get('abstractText'))

    return pd.DataFrame({'id': pmids, 'title': titles, 'abstract': abstracts})


# ---------------------------------------------------------------------------
def run_query(query: str, last_date: str, today: str) -> pd.DataFrame:
    """
    Run query on EuropePMC API
    
    Parameters:
    `query`: Query to use
    `last_date`: Oldest date to use in query
    
    Return: `DataFrame` of returned titles and abstracts
    """

    query = query.format(last_date, today)

    prefix = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query='
    suffix = '&resultType=core&fromSearchPost=false&format=json'
    url = prefix + query + suffix

    results = requests.get(url)
    if not results.status_code == requests.codes.ok:
        results.raise_for_status()

    results_json = cast(dict, results.json())

    return clean_results(results_json)


# ---------------------------------------------------------------------------
def main() -> None:
    """ Main function """

    args = get_args()
    out_dir = args.out_dir

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    out_df, date_out = make_filenames(out_dir)

    today = datetime.today().strftime(r'%Y-%m-%d')

    results = run_query(args.query, args.last_date, today)

    results.to_csv(out_df, index=False)
    print(today, file=open(date_out, 'wt'))

    print(f'Done. Wrote 2 files to {out_dir}.')


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
