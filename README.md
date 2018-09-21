## pinchy
Downloads mixes and associated images from [Pinchy and Friends](http://pinchyandfriends.com)
  
The resulting file structure looks like this:
```
/Users/rorysawyer/media/audio/pinchy/
└── <mix_id>
    ├── <mix_name>.mp3
    ├── <thumbnail>.jpg
    └── tracklist.txt
```
  
### usage
```sh
$ pipenv shell
$ python pinchy.py 
```

### depedencies
- `pipenv`
