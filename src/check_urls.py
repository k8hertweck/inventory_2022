#!/usr/bin/env python3
"""
Purpose: Check URLs
Authors: Kenneth Schackart
"""

import argparse
import logging
import multiprocessing as mp
import os
import time
from functools import partial
from multiprocessing.pool import Pool
from typing import List, NamedTuple, Optional, TextIO, Union, cast

import pandas as pd
import requests
from pandas.testing import assert_frame_equal

from utils import CustomHelpFormatter


# ---------------------------------------------------------------------------
class Args(NamedTuple):
    """ Command-line arguments """
    file: TextIO
    out_dir: str
    num_tries: int
    wait: int
    ncpu: Optional[int]
    verbose: bool


# ---------------------------------------------------------------------------
class URLStatus(NamedTuple):
    """
    URL and its returned status
    """
    url: str
    status: Union[str, int]


# ---------------------------------------------------------------------------
class WayBackSnapshot(NamedTuple):
    """
    Information about a WayBack Archive Snapshot

    `url`: URL of Snapshot on WayBack Machine
    `timestamp`: Timestamp of archive
    `status`: Snapshot status
    """
    url: Optional[str]
    timestamp: Optional[str]
    status: Optional[str]


# ---------------------------------------------------------------------------
def get_args() -> Args:
    """ Parse command-line arguments """

    parser = argparse.ArgumentParser(
        description=('Check extracted URL statuses'),
        formatter_class=CustomHelpFormatter)

    parser.add_argument('file',
                        metavar='FILE',
                        type=argparse.FileType('rt', encoding='ISO-8859-1'),
                        help='CSV File with extracted_url column')
    parser.add_argument('-o',
                        '--out-dir',
                        metavar='DIR',
                        type=str,
                        default='out/',
                        help='Output directory')
    parser.add_argument('-n',
                        '--num-tries',
                        metavar='INT',
                        type=int,
                        default=3,
                        help='Number of tried for checking URL')
    parser.add_argument('-w',
                        '--wait',
                        metavar='TIME',
                        type=int,
                        default=500,
                        help='Time (ms) to wait between tries')
    parser.add_argument('-t',
                        '--ncpu',
                        metavar='CPU',
                        type=int,
                        help=('Number of CPUs for parallel '
                              'processing (default: all)'))
    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        help=('Run with additional messages'))

    args = parser.parse_args()

    return Args(args.file, args.out_dir, args.num_tries, args.wait, args.ncpu,
                args.verbose)


# ---------------------------------------------------------------------------
def expand_url_col(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expand the URL column, by creating a row per URL.
    
    `df`: Dataframe with extracted_url column
    
    Return: Dataframe with row per URL
    """
    logging.debug('Expanding URL column. One row per URL')

    df['extracted_url'] = df['extracted_url'].str.split(', ')

    df = df.explode('extracted_url')

    df.reset_index(drop=True, inplace=True)

    return df


# ---------------------------------------------------------------------------
def test_expand_url_col() -> None:
    """ Test expand_url_col() """

    in_df = pd.DataFrame(
        [[123, 'Some text', 'https://www.google.com, http://google.com'],
         [789, 'Foo', 'https://www.amazon.com/afbadfbnvbadfbaefbnaegn']],
        columns=['ID', 'text', 'extracted_url'])

    out_df = pd.DataFrame(
        [[123, 'Some text', 'https://www.google.com'],
         [123, 'Some text', 'http://google.com'],
         [789, 'Foo', 'https://www.amazon.com/afbadfbnvbadfbaefbnaegn']],
        columns=['ID', 'text', 'extracted_url'])

    assert_frame_equal(expand_url_col(in_df), out_df)


# ---------------------------------------------------------------------------
def get_pool(ncpu: Optional[int]) -> Pool:
    """
    Get Pool for multiprocessing.
    
    Parameters:
    `ncpu`: Number of CPUs to use, if not specified detect number available
    
    Return:
    `Pool` using `ncpu` or number of available CPUs
    """

    n_cpus = ncpu if ncpu else mp.cpu_count()

    logging.debug(f'Running with {n_cpus} processes')

    return mp.Pool(n_cpus)


# ---------------------------------------------------------------------------
def make_filename(out_dir: str, infile_name: str) -> str:
    '''
    Make filename for output reusing input file's basename

    Parameters:
    `outdir`: Output directory

    Return: Output filename
    '''

    return os.path.join(out_dir, os.path.basename(infile_name))


# ---------------------------------------------------------------------------
def test_make_filenames() -> None:
    """ Test make_filenames() """

    assert make_filename(
        'out/checked_urls',
        'out/urls/predictions.csv') == ('out/checked_urls/predictions.csv')


# ---------------------------------------------------------------------------
def request_url(url: str) -> Union[int, str]:
    """
    Check a URL once using try-except to catch exceptions
    
    Parameters:
    `url`: URL string
    
    Return: Status code or error message
    """

    try:
        r = requests.head(url)
    except requests.exceptions.RequestException as err:
        return str(err)

    return r.status_code


# ---------------------------------------------------------------------------
def test_request_url() -> None:
    """ Test request_url() """

    # Hopefully, Google doesn't disappear, if it does use a different URL
    assert request_url('https://www.google.com') == 200

    # Bad URLs
    assert request_url('http://google.com') == 301
    assert request_url('https://www.amazon.com/afbadfbnvbadfbaefbnaegn') == 404

    # Runtime exception
    assert request_url('adflkbndijfbn') == (
        "Invalid URL 'adflkbndijfbn': No scheme supplied. "
        "Perhaps you meant http://adflkbndijfbn?")


# ---------------------------------------------------------------------------
def check_url(url: str, num_tries: int, wait: int) -> URLStatus:
    """
    Try requesting URL the specified number of tries, returning 200
    if it succeeds at least once

    Parameters:
    `url`: URL string
    `num_tries`: Number of times to try requesting URL
    `wait`: Wait time between tries in ms

    Return: Status code or error message
    """

    for _ in range(num_tries):
        status = request_url(url)
        if status == 200:
            break
        time.sleep(wait / 1000)

    return URLStatus(url, status)


# ---------------------------------------------------------------------------
def test_check_url() -> None:
    """ Test check_url() """

    assert check_url('https://www.google.com', 3,
                     0) == URLStatus('https://www.google.com', 200)

    # Bad URLs
    assert check_url('http://google.com', 3,
                     0) == URLStatus('http://google.com', 301)
    assert check_url('https://www.amazon.com/afbadffbaefbnaegn', 3,
                     250) == URLStatus(
                         'https://www.amazon.com/afbadffbaefbnaegn', 404)

    # Runtime exception
    assert check_url('adflkbndijfbn', 3, 250) == URLStatus(
        'adflkbndijfbn', ("Invalid URL 'adflkbndijfbn': No scheme supplied. "
                          "Perhaps you meant http://adflkbndijfbn?"))


# ---------------------------------------------------------------------------
def merge_url_statuses(df: pd.DataFrame,
                       url_statuses: List[URLStatus]) -> pd.DataFrame:
    """
    Create column of URL statuses
    
    Parameters:
    `df`: Dataframe containing extracted_url column
    `url_statuses`: List of `URLStatus` objects
    
    Return: Same dataframe, with addition extracted_url_status column
    """

    url_dict = {x.url: x.status for x in url_statuses}

    df['extracted_url_status'] = df['extracted_url'].map(url_dict)

    return df


# ---------------------------------------------------------------------------
def test_merge_url_statuses() -> None:
    """ Test merge_url_statuses() """

    in_df = pd.DataFrame([[123, 'Some text', 'https://www.google.com'],
                          [456, 'More text', 'http://google.com']],
                         columns=['ID', 'text', 'extracted_url'])

    statuses = [
        URLStatus('http://google.com', 301),
        URLStatus('https://www.google.com', 200)
    ]

    out_df = pd.DataFrame(
        [[123, 'Some text', 'https://www.google.com', 200],
         [456, 'More text', 'http://google.com', 301]],
        columns=['ID', 'text', 'extracted_url', 'extracted_url_status'])

    assert_frame_equal(merge_url_statuses(in_df, statuses), out_df)


# ---------------------------------------------------------------------------
def check_wayback(url: str) -> WayBackSnapshot:
    """
    Check the WayBack Machine for an archived version of requested URL.

    Parameters:
    `url`: URL to check

    Return: A `WayBackSnapshot` NamedTuple
    with attributes `url`, `timestamp`, and `status`
    """

    # Not using try-except because if there is an exception it is not
    # because there is not an archived version, it means the API
    # has changed.
    r = requests.get(f'http://archive.org/wayback/available?url={url}',
                     headers={'User-agent': 'biodata_resource_inventory'})

    returned_dict = cast(dict, r.json())
    snapshots = cast(dict, returned_dict.get('archived_snapshots'))

    if not snapshots:
        return 'no_wayback'

    snapshot = cast(dict, snapshots.get('closest'))

    return snapshot.get('url')


# ---------------------------------------------------------------------------
def test_check_wayback() -> None:
    """ Test check_wayback() """

    # Example from their website
    assert check_wayback('example.com') != ''

    # Valid URL, but not present as a snapshot

    # Invalid URL
    assert check_wayback('aegkbnwefnb') == 'no_wayback'


# ---------------------------------------------------------------------------
def check_urls(df: pd.DataFrame, ncpu: Optional[int], num_tries: int,
               wait: int) -> pd.DataFrame:
    """
    Check all URLs in df
    
    Parameters:
    `df`: Dataframe with url column
    
    Return: Dataframe
    """

    check_url_part = partial(check_url, num_tries=num_tries, wait=wait)

    with get_pool(ncpu) as pool:
        logging.debug('Checking extracted URL statuses.\n'
                      f'\tMax attempts: {num_tries}.\n'
                      f'\tTime between attempts: {wait} ms.')

        url_statuses = pool.map_async(check_url_part,
                                      df['extracted_url']).get()

        df = merge_url_statuses(df, url_statuses)

        df['extracted_url_status']

        logging.debug('Finished checking extracted URLs.')
        logging.debug('Checking for snapshots of extracted URLs '
                      'on WayBack Machine.')

        df['wayback_url'] = df['extracted_url'].map(check_wayback)

        logging.debug('Finished checking WayBack Machine.')

    return df


# ---------------------------------------------------------------------------
def test_check_urls() -> None:
    """ Test check_urls() """

    in_df = pd.DataFrame(
        [[123, 'Some text', 'https://www.google.com'],
         [456, 'More text', 'http://google.com'],
         [789, 'Foo', 'https://www.amazon.com/afbadfbnvbadfbaefbnaegn']],
        columns=['ID', 'text', 'extracted_url'])

    returned_df = check_urls(in_df, None, 3, 0)
    returned_df.sort_values('ID', inplace=True)

    # Correct number of rows
    assert len(returned_df) == 3

    # Correct columns
    assert all(x == y for x, y in zip(returned_df.columns, [
        'ID', 'text', 'extracted_url', 'extracted_url_status', 'wayback_url'
    ]))


# ---------------------------------------------------------------------------
def regroup_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regroup dataframe to contain one row per article, columns may contain
    list elements
    
    `df`: Dataframe with one row per URL
    
    Return: Dataframe with one row per article
    """

    logging.debug('Collapsing columns. One row per article')
    df['extracted_url_status'] = df['extracted_url_status'].astype(str)
    df['extracted_url'] = df['extracted_url'].astype(str)
    df['wayback_url'] = df['wayback_url'].astype(str)

    out_df = (df.groupby(['ID', 'text']).agg({
        'extracted_url':
        lambda x: ', '.join(x),
        'extracted_url_status':
        lambda x: ', '.join(x),
        'wayback_url':
        lambda x: ', '.join(x)
    }).reset_index())

    return out_df


# ---------------------------------------------------------------------------
def test_regroup_df() -> None:
    """ Test regroup_df() """

    in_df = pd.DataFrame(
        [[123, 'Some text', 'https://www.google.com', 200, 'wayback_google'],
         [123, 'Some text', 'http://google.com', 301, 'no_wayback'],
         [
             789, 'Foo', 'https://www.amazon.com/afbadfbnvbadfbaefbnaegn', 404,
             'no_wayback'
         ]],
        columns=[
            'ID', 'text', 'extracted_url', 'extracted_url_status',
            'wayback_url'
        ])

    out_df = pd.DataFrame(
        [[
            123, 'Some text', 'https://www.google.com, http://google.com',
            '200, 301', 'wayback_google, no_wayback'
        ],
         [
             789, 'Foo', 'https://www.amazon.com/afbadfbnvbadfbaefbnaegn',
             '404', 'no_wayback'
         ]],
        columns=[
            'ID', 'text', 'extracted_url', 'extracted_url_status',
            'wayback_url'
        ])

    assert_frame_equal(regroup_df(in_df), out_df)


# ---------------------------------------------------------------------------
def main() -> None:
    """ Main function """

    args = get_args()
    out_dir = args.out_dir

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    logging.debug(f'Reading input file: {args.file.name}.')
    df = pd.read_csv(args.file)

    df = expand_url_col(df)
    df = check_urls(df, args.ncpu, args.num_tries, args.wait)
    df = regroup_df(df)

    outfile = make_filename(out_dir, args.file.name)
    df.to_csv(outfile, index=False)
    
    print(f'Done. Wrote output to {outfile}.')


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
