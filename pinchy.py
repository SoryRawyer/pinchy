"""
pinchy.py — download mixes from pinchyandfriends.com
"""

import os
import requests

from bs4 import BeautifulSoup

# storage dir: keep one directory per mix
# directory will have:
# - mp3
# - artwork
# - tracklist (if available)
LOCAL_DIR = os.path.expanduser('~/media/audio/pinchy/')

BASE_URL = 'http://pinchyandfriends.com'

class PinchyMixMetadata(object):
    """
    PinchyMixMetadata : class for storing pinchy mix metadata
    """

    def __init__(self, *args, **kwargs):
        for kwarg in kwargs:
            setattr(self, kwarg, kwargs[kwarg])


    @staticmethod
    def new(div):
        """
        new : parse the div and return a new PinchyMixMetadata object
        """
        mix_name = div['data-name1']
        artist = div['data-name2']
        rel = div['onclick'].split('=')[1].strip().replace("'", '').replace(';', '')[1:]
        mix_id = rel.split('/')[0]
        return PinchyMixMetadata(artist=artist, mix_name=mix_name, mix_id=mix_id, rel=rel)


def get_existing_mix_ids():
    """
    get_existing_mix_ids — return a list of pinchy mix ids
    creates directory if not already present
    """
    if not os.path.isdir(LOCAL_DIR):
        os.makedirs(LOCAL_DIR)
        return []

    mix_dir = lambda x: os.path.join(LOCAL_DIR, x)
    return set([mix for mix in os.listdir(LOCAL_DIR) if os.path.isdir(mix_dir(mix))])


def get_available_pinchy_info(content):
    """
    get_available_pinchy_info

    parse the html provided and return a list of dictionaries

    all the mixes will be under the div with the id 'grid'
    each div looks like this:
    <div class="grid_img hand" data-name1="Axe to Grind" data-name2="Lovefingers" data-color="#51AEFF" style="left:0px; top:0px;" onclick="window.location = '/5170/axe-to-grind/';">
        <img src="/thumbs/440x440/files/zc/lovefingers_97960.jpg" width="150" height="150" class="imgOff" onload="$(this).fadeIn(300);" style="display: inline;">
    </div>

    data-name1 = mix name
    data-name2 = artist name
    onclick = "window.location = '/<mix_id>/<url-friendly-mix-name>/'"
    """
    page = BeautifulSoup(content, features='html.parser')
    rel = page.find(id='grid_rel')
    return [PinchyMixMetadata.new(child) for child in rel.children if child.name == 'div']


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
    with open(local_name, 'wb') as output:
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                output.write(chunk)
    return


def scrape_mix_page_and_download(mix):
    """
    scrape_mix_page_and_download

    get next page
    create directory for mix
    download mix and photo and tracklist
    """
    url = os.path.join(BASE_URL, mix.rel)
    resp = requests.get(url)
    resp.raise_for_status() # handle this later, too

    soup = BeautifulSoup(resp.content)
    dl_link = soup.find(id='download').a['href']
    grid = soup.find(id='grid')
    img_rel_link = grid.img['src'][0:]
    tracklist = grid.p.string

    local_mix_dir = os.path.join(LOCAL_DIR, mix.mix_id)
    if not os.path.isdir(local_mix_dir):
        os.makedirs(local_mix_dir)

    mix_file_name = os.path.join(local_mix_dir, os.path.split(dl_link)[1])
    download_file(mix_file_name, dl_link)

    img_file_name = os.path.join(local_mix_dir, os.path.split(img_rel_link)[1])
    img_dl_link = os.path.join(BASE_URL)
    download_file(img_file_name, img_dl_link)

    tracklist_file_name = os.path.join(local_mix_dir, 'tracklist.txt')
    with open(tracklist_file_name, 'w') as tracklist_file:
        tracklist_file.write(tracklist)

    return


def main():
    """
    main :
    - bootstrap (get a list of all downloaded mixes)
    - scrape pinchyandfriends.com and look for IDs that aren't found locally
    - download 'em and exit
        - if present, save the tracklist
    """
    mix_ids = get_existing_mix_ids()
    resp = requests.get(BASE_URL)
    resp.raise_for_status() # handle this later
    mixes = [mix for mix in get_available_pinchy_info(resp.content) if mix.mix_id not in mix_ids]
    for mix in mixes:
        scrape_mix_page_and_download(mix)


if __name__ == '__main__':
    main()
