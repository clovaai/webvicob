<div align="center">
    
# WEBVICOB 🕸 : WEB based VIsual COrpus Builder

[![Paper](https://img.shields.io/badge/Paper-arxiv.xxxx.xxxx-red)](#)
[![Pypi](https://img.shields.io/badge/python->=3.8-blue)](#)

Official Implementation of WEB based VIsual COrpus Builder(WEBVICOB)  

</div>

![annot](resources/annot.png)

## Updates

**_2022-11-04_** First Commit, We release the codebase.

## How to Use

### Environment
python >= 3.8

##### Init submodule (google font)
We use GoogleFonts for various visual information. (font/google)  
Init submodule if you want to use it.     

```bash
$ git submodule update --init --recursive
```

##### Install dependencies (Tested on ubuntu18.04)
```bash
$ bash install_dependencies.sh
```

##### Install python packages 
```bash
$ pip install -U six wheel setuptools
$ pip install -r requirements.txt
```

### Run
JUST DO IT FIRST !! RUN FOLLOWING SCRIPT !!  
To visualize outputs, you should use "debug" option.
```bash
$ PYTHONPATH=$PWD python webvicob/wikipedia/wikipedia.py \
    --chrome_path=/path/to/your/chrome/driver \
    --workspace=./resources/workspace_example \
    --target_lang=en \
    --num_train=10 \
    --num_val=1 \
    --num_test=1 \
    --debug=True
```

#### Available options
| option | default | desc                                                                                                                                                                                                              |
|---|---|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| workspace (str) | ./ | Dir to load json files and save lmdb.                                                                                                                                                                             |
| target_lang (str) | ja | Whatever you want.                                                                                                                                                                                                |
| num_train (int) | -1 | Number of train samples.                                                                                                                                                                                          |
| num_val (int) | 0 | Number of val samples.                                                                                                                                                                                            |
| num_test (int) | 0 | Number of test samples.                                                                                                                                                                                           |
| debug (bool) | False | Debug option.                                                                                                                                                                                                     |
| num_process (int) | -1 | Number of processes. -1 ==> os.cpu_count() value is used.                                                                                                                                                         |
| shrink_heuristic (bool) | True | Use heuristic shrinking of character boxes.                                                                                                                                                                       |
| remove_background (bool) | True | Remove background img of html.                                                                                                                                                                                    |
| unroll_contents (bool) | False | Unroll html contents.                                                                                                                                                                                             |
| change_para_font (bool) | True | Change paragraph fonts with google-fonts.                                                                                                                                                                         |
| sleep_time (int) | 1 | sleep time for every render.                                                                                                                                                                                      |
| capture_widths (tuple[int]) | (800, 1200, 1600) | Randomly select capture width. This is different from final_width. This option determines the width of the browser when rendering. final_width is an option to resize the finally rendered image and annotations. |
| capture_height_limit (int) | 16384 | Skip the rendering process if rendered page's height is larger than the limit value.                                                                                                                              |
| final_width (int) | None | Final save img width size. (Useful when you do not have a lot of storage)                                                                                                                                         |
| chunk_idx (int) | None | Chunk index of json_list. Useful when you have multiple computers.                                                                                                                                                |
| total_chunk (int) | None | Total number of chunks of json_list.                                                                                                                                                                              |

### Prepare Dataset
We made sample ndjson files on resources/workspace_example.  
Each sample ndjson files has 100 samples.  

If you want to download whole crawled data,  
Download ndjson files (`[lang]wiki-NS0-[version]-ENTERPRISE-HTML.json.tar.gz`) at https://dumps.wikimedia.org/other/enterprise_html/runs  
And untar ndjson files on `[your workspace path]/raw`.

### Visualization

|character|word|line|paragraph|image|
|---|---|---|---|---|
| <img src="resources/visualize_examples/char.jpg" width="200" height="400"> | <img src="resources/visualize_examples/word.jpg" width="200" height="400"> | <img src="resources/visualize_examples/line.jpg" width="200" height="400">|<img src="resources/visualize_examples/paragraph.jpg" width="200" height="400">|<img src="resources/visualize_examples/image.jpg" width="200" height="400">|

## How to Cite
If you find this work useful to you, please cite:
```
@article{kim2022web,
   title={WEB based VIsual COrpus Builder},
   author={Kim, Donghyun and Kim, Yoonsik and Hong, Teakgyu and Yim, Moonbin and Kim, Geewook},
   journal={arXiv preprint arXiv:xxxx.xxxx},
   year={2022}
}
```

## How to Contribute
Please use pre-commit which uses Black and Isort.
```
$ pip install pre-commit
$ pre-commit install
```

##### Step By Step
1. Open new issue.
2. Match code style (black, isort)
    1. execute commands in webvicob directory.
    2. `black .`
    3. `isort --profile black .`
4. Write test code.
5. Branch ([date]\_[whatever]).
6. Delete branch after Squash&Merge.

Required Approve: 1  