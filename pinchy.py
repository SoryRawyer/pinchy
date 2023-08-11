"""
pinchy.py - download mixes from pinchyandfriends.com
"""

import argparse
import logging
import os

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import requests

from bs4 import BeautifulSoup
from supabase import Client, create_client

# storage dir: keep one directory per mix
# directory will have:
# - mp3
# - artwork
# - tracklist (if available)
LOCAL_DIR = os.path.expanduser("~/media/audio/pinchy/")

BASE_URL = "http://pinchyandfriends.com"

MIX_TABLE = "pinchy_mixes"

log = logging.getLogger("pinchy")


def get_supa_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET"])


@dataclass
class PinchyMixMetadata:
    """
    PinchyMixMetadata : class for storing pinchy mix metadata
    """

    mix_name: str
    artist: str
    mix_landing_url: str
    mix_id: str

    @staticmethod
    def from_div(div):
        """
        new : parse the div and return a new PinchyMixMetadata object
        """
        mix_name = div["data-name2"]
        artist = div["data-name1"]
        rel = div["onclick"].split("=")[1].strip().replace("'", "").replace(";", "")[1:]
        mix_id = rel.split("/")[0]
        return PinchyMixMetadata(artist, mix_name, rel, mix_id)


def format_mix_info(mixes):
    """
    Create a table based on the list of pinchy mixes
    Pads out the titles based on the widest name in the list
    """
    artist_len = max([len(mix.artist) for mix in mixes])
    title_len = max([len(mix.mix_name) for mix in mixes])
    separator = f"|{''.ljust(artist_len + title_len + 1, '=')}|"
    header = [
        separator,
        f"|{'artist'.ljust(artist_len)}|{'mix name'.ljust(title_len)}|",
        separator,
    ]
    footer = [separator]
    return "\n".join(
        header
        + [
            f"|{mix.artist.ljust(artist_len)}|{mix.mix_name.ljust(title_len)}|"
            for mix in mixes
        ]
        + footer
    )


def get_existing_mix_ids():
    """
    get_existing_mix_ids — return a list of pinchy mix ids
    creates directory if not already present
    """
    if not os.path.isdir(LOCAL_DIR):
        os.makedirs(LOCAL_DIR)
        return []

    mix_dir = lambda x: os.path.join(LOCAL_DIR, x)
    return {mix for mix in os.listdir(LOCAL_DIR) if os.path.isdir(mix_dir(mix))}


def get_available_pinchy_info(content):
    """
    get_available_pinchy_info

    parse the html provided and return a list of dictionaries

    all the mixes will be under the div with the id 'grid'
    each div looks like this:
    <div class="grid_img hand" data-name1="Axe to Grind"
    data-name2="Lovefingers" data-color="#51AEFF"
    style="left:0px; top:0px;"
    onclick="window.location = '/5170/axe-to-grind/';">
        <img src="/thumbs/440x440/files/zc/lovefingers_97960.jpg" width="150"
        height="150" class="imgOff" onload="$(this).fadeIn(300);"
        style="display: inline;">
    </div>

    data-name1 = mix name
    data-name2 = artist name
    onclick = "window.location = '/<mix_id>/<url-friendly-mix-name>/'"
    """
    page = BeautifulSoup(content, features="html.parser")
    rel = page.find(id="grid_rel")
    return [
        PinchyMixMetadata.from_div(child)
        for child in rel.children
        if child.name == "div"
    ]


def download_file(local_name, url, overwrite=False):
    """
    download_file
    stream a file from the given url to the given local filename
    if the local file already exists, do not overwrite it unless told
    to do so
    """
    if os.path.isfile(local_name) and not overwrite:
        return
    resp = requests.get(url, stream=True)
    with open(local_name, "wb") as output:
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                output.write(chunk)


def location(track: PinchyMixMetadata, filename: str) -> str:
    """
    given a track, return a relative path to the mix
    """
    return os.path.join(track.mix_id, filename)


def write_to_supa(
    client: Client, track: PinchyMixMetadata, location: str, art_location: Optional[str]
):
    """
    write mix information to supabase
    """
    data = {
        "pinchy_id": int(track.mix_id),
        "name": track.mix_name,
        "artist_name": track.artist,
        "location": location,
        "art_location": art_location,
    }
    client.table(MIX_TABLE).insert(data).execute()


def upload_to_supa(client: Client, locations: dict[str, str]):
    """
    take a dictionary of image/mix locations and upload file to supabase
    """
    storage = client.storage()
    file_storage = storage.StorageFileAPI("pinchy-files")
    for key, local_filename in locations.items():
        # key is the path in the supabase bucket
        # local_filename is the local path where the data is stored
        file_storage.upload(os.path.join("pinchy-files", key), local_filename)


def get_mix_page_details(mix: PinchyMixMetadata):
    url = os.path.join(BASE_URL, mix.mix_landing_url)
    resp = requests.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content)
    dl_link = soup.find(id="download").a["href"]
    grid = soup.find(id="grid")
    img_rel_link = grid.img["src"][0:]
    tracklist = grid.p.string
    return {
        "download": dl_link,
        "img": img_rel_link,
        "tracklist": tracklist,
    }


def scrape_mix_page_and_download(mix: PinchyMixMetadata):
    """
    scrape_mix_page_and_download

    get next page
    create directory for mix
    download mix and photo and tracklist
    """
    log.info("downloading {}".format(mix.mix_name))
    url = os.path.join(BASE_URL, mix.mix_landing_url)
    resp = requests.get(url)
    resp.raise_for_status()  # handle this later, too

    soup = BeautifulSoup(resp.content)
    dl_link = soup.find(id="download").a["href"]
    mix_filename = os.path.split(dl_link)[1]
    grid = soup.find(id="grid")
    img_rel_link = grid.img["src"][0:]
    art_filename = os.path.split(img_rel_link)[1]
    tracklist = grid.p.string

    local_mix_dir = os.path.join(LOCAL_DIR, mix.mix_id)
    if not os.path.isdir(local_mix_dir):
        os.makedirs(local_mix_dir)

    # TODO: use this as the supabase path, mostly
    # just, like, remove all the stuff that's only relevant for the local filesystem
    mix_file_name = os.path.join(local_mix_dir, mix_filename)
    download_file(mix_file_name, dl_link)

    img_file_name = os.path.join(local_mix_dir, art_filename)
    img_dl_link = os.path.join(BASE_URL)
    download_file(img_file_name, img_dl_link)

    tracklist_file_name = os.path.join(local_mix_dir, "tracklist.txt")
    with open(tracklist_file_name, "w") as tracklist_file:
        tracklist_file.write(tracklist)

    client = get_supa_client()
    mix_loc = location(mix, mix_filename)
    art_loc = location(mix, art_filename)
    write_to_supa(client, mix, mix_loc, art_loc)
    # write the files to storage

    return


def get_pinchy_homepage():
    """
    ye olde http request
    """
    resp = requests.get(BASE_URL)
    resp.raise_for_status()  # handle this later
    return resp.content


def get_args():
    """
    get_args:
    - parse command-line arguments
    list: show which mixes you have locally and also mixes that at one the site
    download: save the mixes locally
    publish: push the mixes somewhere (maybe add a value that indicates
    where to publish?? like gcp or aws or dropbox or whatever?)
    """
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--list", help="Print all local and remote mixes", action="store_true"
    )
    group.add_argument("--download", help="Download mixes only", action="store_true")
    group.add_argument(
        "--upload", help="Upload mixes to google play", action="store_true"
    )
    group.add_argument(
        "--threads",
        default=1,
        help="number of threads to use. default is single-threaded",
    )
    return parser.parse_args()


def main():
    """
    main :
    - bootstrap (get a list of all downloaded mixes)
    - scrape pinchyandfriends.com and look for IDs that aren't found locally
    - if list: print downloaded mixes + mixes available on the site
    - if download: just download any remote mixes and exit
    - if upload: download any remote mixes not found locally/in google play
        - if present, save the tracklist
    """
    args = get_args()
    mix_ids = get_existing_mix_ids()
    mixes = [
        mix
        for mix in get_available_pinchy_info(get_pinchy_homepage())
        if mix.mix_id not in mix_ids
    ]
    if args.list:
        print(format_mix_info(mixes))
        return
    if args.download:
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            for mix in mixes:
                executor.submit(scrape_mix_page_and_download, mix)
                # now that the mix is downloaded loally, we should also upload all
                # this to supabase


if __name__ == "__main__":
    main()
