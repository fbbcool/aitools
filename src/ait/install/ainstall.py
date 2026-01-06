import os
import sys
from typing import Final, Generator, Literal, Any
import json
from huggingface_hub import hf_hub_download, snapshot_download
import requests
from tqdm import tqdm
from git import Repo  # pip install gitpython
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from pprint import pprint

AIT_PATH_CONF: Final = f'{os.environ["CONF_AIT"]}/models'
AIT_PATH_CACHE: Final = f'{os.environ["HOME"]}/.cache/ainstall'
AIT_MODEL_PREFIXES: Final = ['models_', 'ainst_']


class AInstallerDB:
    def __init__(self, srcdir: str = AIT_PATH_CONF, prefixes: list[str] = AIT_MODEL_PREFIXES):
        self._db: dict = {}
        self._srcdir: Path = Path(srcdir)
        self._prefixes: list[str] = prefixes

        self._make()

    def _make(self) -> None:
        """
        schema: /group/variant/target/[target_config]
        """
        files = []
        for prefix in self._prefixes:
            for file in self._srcdir.glob(f'{prefix}*.json'):
                files.append(file)

        for file in files:
            print(f'read {file.name}')
            with file.open() as json_data:
                groups = json.load(json_data)
            for group, update_data in groups.items():
                self._update_group(group, update_data)

    def _update_group(self, group: str, data: dict) -> None:
        group_data = self._db.get(group, {})
        for variant, update_data in data.items():
            variant_data = group_data.get(variant, {})
            group_data[variant] = self._update_variant(variant_data, update_data)
        self._db[group] = group_data

    def _update_variant(self, variant: dict, data: dict) -> dict:
        for target, update_data in data.items():
            target_data = variant.get(target, [])
            target_data += update_data
            variant[target] = target_data
        return variant

    @property
    def db(self) -> dict:
        return self._db

    def repo_ids(self, group: str, variant: str, target: str) -> list[str]:
        _group: dict = self.db.get(group, {})
        if not _group:
            return []
        _variant = _group.get(variant, {})
        if not _variant:
            return []
        targets = _variant.get(target, [])

        repo_ids = []
        for _target in targets:
            repo_id = _target.get('repo_id', '')
            if repo_id:
                repo_ids.append(repo_id)

        return repo_ids


class AInstaller:
    CHUNK_SIZE: Final = 1638400
    USER_AGENT: Final = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'  # noqa

    def __init__(
        self,
        base_dir: str | Path,
        group: str = '',
        method: Literal['comfyui', 'diffpipe'] = 'comfyui',
        verbose: bool = False,
    ):
        self.db = AInstallerDB().db
        self._cache = Path(AIT_PATH_CACHE)
        self._cache.mkdir(parents=True, exist_ok=True)
        self._vars_bound: dict[str, Any] = {}

        self.base_dir = Path(base_dir)
        split = group.split(':')
        self.group = split[0]
        self.variants = []
        if len(split) > 1:
            self.variants.append('common')
            self.variants.append(split[1])
        self.type = method
        self.requirements = []

        self.token_cai = os.environ.get('CAI_TOKEN', '')

        self.verbose = verbose

        self.install()

    def install(self):
        for item in self._items:
            try:
                item = self._install_item(item)
            except Exception as e:
                print(f"warning: couldn't install {item}: {e}")
                continue

            target_var = item.get('target_var', None)
            if target_var is not None:
                var_value = item.get('link', None)
                if var_value is None:
                    continue
                split = target_var.split(':')
                var_bound = split[0]
                var_type = 'str'
                if len(split) > 1:
                    var_type = split[1]

                if var_type == 'str':
                    var_value = str(var_value)
                elif var_type == 'int':
                    var_value = int(var_value)
                elif var_type == 'float':
                    var_value = float(var_value)
                elif var_type == 'list_str':
                    var_value = [str(var_value)]
                elif var_type == 'list_int':
                    var_value = [int(var_value)]
                elif var_type == 'list_float':
                    var_value = [float(var_value)]
                self._vars_bound |= {var_bound: var_value}

        # create python requirements.txt
        self.requirements = list(set(self.requirements))

        if self.requirements:
            requirements_txt = self.base_dir / 'requirements_ainstall.txt'
            with requirements_txt.open('w') as f:
                f.write('\n'.join(self.requirements))

    @property
    def vars_bound(self) -> dict:
        return self._vars_bound

    @property
    def variant(self) -> str | None:
        variant = None
        common = 'common'  # skip this one, no explicit variant!
        if len(self.variants) == 1:
            variant = self.variants[0]
            if variant == common:
                variant = None
        elif len(self.variants) == 2:
            variant = self.variants[0]
            if variant == common:
                variant = self.variants[1]
        else:
            variant = None  # no explicit variant
        return variant

    @property
    def _items(self) -> Generator:
        # selected group
        print(f'items for selected group {self.group}:')
        group = self.db.get(self.group, {})
        for variant, _ in group.items():
            # no variants given => install all
            # variants given => iinstall explicit
            if self.variants:
                if variant not in self.variants:
                    continue

            variant_data: dict = group.get(variant, {})
            if not variant_data:
                continue

            for target, target_data in variant_data.items():
                for config in target_data:
                    if config.get('skip', False):
                        continue
                    if config.get('action', 'None') == 'skip':
                        continue
                    yield self._make_item(self.group, variant, target, config)

    def _make_item(self, group: str, variant: str, target: str, config: dict):
        item: dict = {
            'group': group,
            'variant': variant,
            'target': target,
            'config': config,
            'type': self.type,
        }

        # resolve download method
        method_download = item['config'].get('method_download', 'auto')

        if method_download == 'auto':
            if item['target'] == 'custom_node':
                method_download = 'github'
        if method_download == 'auto':
            if item['config'].get('link', None) is not None:
                method_download = 'civitai'
            elif item['config'].get('repo_id', None) is not None:
                method_download = 'huggingface'

        if method_download == 'auto':
            # auto couldn't be resolved
            print("Warning: auto download method couldn't be resolved.")

        item['config'] |= {'method_download': method_download}

        return item

    def _install_item(self, item: dict) -> dict:
        str_setup = f'_setup_item_{item["type"]}'
        setup = getattr(self, str_setup, None)
        if callable(setup):
            item = setup(item)
        else:
            print(f'warning: no item setup for type[{item["type"]}]')
        return self._install_item_generic(item)

    def _install_item_generic(self, item: dict) -> dict:
        if self.verbose:
            pprint(item)
        if item.get('invalid', False):
            print('warning: item is invalid!')
            return {}
        target_dir = item.get('target_dir', '')
        if not target_dir:
            print('warning: item has no target directory!')
            return {}

        config = item.get('config', {})
        method = config.get('method_download', '')

        descriptor = self._descriptor_item(item)
        print(f'[{method}] retrieving {descriptor} ...')

        if not method:
            print('warning: item has no download method!')
            return {}
        elif method == 'huggingface':
            item = self._install_item_hf(item)
        elif method == 'github':
            item = self._install_item_git(item)
        elif method == 'civitai':
            item = self._install_item_civitai(item)
        elif method == 'wget':
            item = self._install_item_wget(item)

        return item

    def _setup_item_comfyui(self, item: dict) -> dict:
        # build target url
        map_target_dirs = {
            'ckpt': 'models/ckpt',
            'vae': 'models/vae',
            'controlnet': 'models/controlnet',
            'custom_node': 'custom_nodes',
            'lora': 'models/loras',
            'embedding': 'models/embeddings',
            'clip': 'models/clip',
            'clip_vision': 'models/clip_vision',
            'ipadapter': 'models/ipadapter',
            'unet': 'models/unet',
            'upscale': 'models/upscale_models',
            'diffusor': 'models/diffusion_models',
            'transformer': 'models/diffusion_models',
            'text_encoder': 'models/text_encoders',
        }
        target_dir = map_target_dirs.get(item.get('target', 'unknown'), '')
        if not target_dir:
            item['invalid'] = True
            return item
        target = item.get('target')
        if target == 'custom_node':
            repo_id = item['config'].get('repo_id')
            split = repo_id.split('/')
            # add name of repo id to target directory
            target_dir = f'{target_dir}/{split[1]}'

        group = item.get('group', 'comfyui')
        target_dir = Path(target_dir)
        if group != self.type:
            target_dir = target_dir / group

        variant = item.get('variant', 'common')
        if variant != 'common':
            target_dir = target_dir / variant

        # apply subdir
        subdir = item['config'].get('subdir', '')
        file: str = item['config'].get('file', '')
        if subdir:
            if subdir == 'auto':
                # check for high/low
                if 'high' in file.lower():
                    subdir = 'high'
                if 'low' in file.lower():
                    subdir = 'low'
            if subdir != 'auto':
                target_dir = target_dir / subdir

        target_dir = self.base_dir / target_dir
        item['target_dir'] = str(target_dir)

        return item

    def _setup_item_diffpipe(self, item: dict) -> dict:
        # build target vars for templater
        map_target_vars = {
            'ckpt': 'model___ckpt_path:str',
            'diffuser': 'model___diffusers_path:str',
            'vae': 'model___vae_path:str',
            'lora': 'model___merge_adapters:list_str',
            'clip': 'model___clip_path:str',
            'transformer': 'model___transformer_path:str',
            'text_encoder': 'model___llm_path:str',
        }
        # build target url
        map_target_dirs = {
            'ckpt': 'data/ckpt',
            'dataset': 'data/datasets',
            'vae': 'data/vae',
            'controlnet': 'data/controlnet',
            'lora': 'data/loras',
            'embedding': 'data/embeddings',
            'clip': 'data/clip',
            'clip_vision': 'data/clip_vision',
            'ipadapter': 'data/ipadapter',
            'unet': 'data/unet',
            'upscale': 'data/upscale_models',
            'diffuser': 'data/diffusion_models',
            'transformer': 'data/diffusion_models',
            'text_encoder': 'data/text_encoders',
        }
        target_dir = map_target_dirs.get(item.get('target', 'unknown'), '')
        target_var = map_target_vars.get(item.get('target', 'unknown'), '')
        if not target_dir:
            item['invalid'] = True
            return item
        target = item.get('target')
        if target == 'custom_node':
            repo_id = item['config'].get('repo_id')
            split = repo_id.split('/')
            # add name of repo id to target directory
            target_dir = f'{target_dir}/{split[1]}'

        group = item.get('group', 'comfyui')
        target_dir = Path(target_dir)
        if group != self.type:
            target_dir = target_dir / group

        variant = item.get('variant', 'common')
        if variant != 'common':
            target_dir = target_dir / variant

        # apply subdir
        subdir = item['config'].get('subdir', '')
        file: str = item['config'].get('file', '')
        if subdir:
            if subdir == 'auto':
                # check for high/low
                if 'high' in file.lower():
                    subdir = 'high'
                if 'low' in file.lower():
                    subdir = 'low'
            if subdir != 'auto':
                target_dir = target_dir / subdir

        target_dir = self.base_dir / target_dir
        item['target_dir'] = str(target_dir)
        if target_var:
            item['target_var'] = target_var

        return item

    def _install_item_hf(self, item: dict) -> dict:
        repo_id = item['config'].get('repo_id')
        repo_type = item['config'].get('repo_type', None)
        file = item['config'].get('file', '')
        rename = item['config'].get('rename', '')
        action = item['config'].get('action', '')
        ignore_patterns = item['config'].get('ignore_patterns', [])

        target_dir = Path(item['target_dir'])

        if not file:
            # use snaphot download
            print(f'ignore_patterns: {ignore_patterns}')
            link = Path(
                snapshot_download(
                    repo_id=repo_id, repo_type=repo_type, ignore_patterns=ignore_patterns
                )
            )
            if action == 'link_safetensors':
                for src in Path(link).rglob('*.safetensors'):
                    target = target_dir / Path(src).relative_to(link)
                    self._symlink(src, target)
            elif action != 'no_link':
                target = target_dir / Path(repo_id)
                self._symlink(link, target, directory=True)
                item['link'] = str(target)

        else:
            # use hf download
            link = hf_hub_download(repo_id=repo_id, filename=file)
            src = Path(link)

            if action != 'no_link':
                target_file = src.name
                if rename:
                    target_file = Path(rename).with_suffix(src.suffix)
                target = target_dir / target_file
                self._symlink(src, target)
                item['link'] = str(target)

        return item

    def _install_item_git(self, item: dict) -> dict:
        repo_id = item['config'].get('repo_id')
        target_dir = Path(item['target_dir'])

        url = f'https://github.com/{repo_id}.git'
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        try:
            Repo.clone_from(url, target_dir, recursive=True)
        except Exception as e:
            print(f'Url git clone went wrong: {url} -> {target_dir}')
            print(e)
        finally:
            item['link'] = str(target_dir)
        # collect python requirements
        requirements_txt = target_dir / 'requirements.txt'
        if requirements_txt.exists():
            with requirements_txt.open() as f:
                while line := f.readline():
                    split = line.split('>=')
                    self.requirements.append(split[0].rstrip())
        return item

    def _install_item_wget(self, item: dict) -> dict:
        url = item['config'].get('link', '')
        if not url:
            print('Warning: wget, no link given')
            return {}
        urlp = urlparse(url)
        urlpath = Path(urlp.path)
        urlname = urlpath.name

        rename = item['config'].get('rename', '')
        if not url:
            print('Warning: wget, no rename given')
            return {}
        target_dir = Path(item['target_dir'])
        target_dir.mkdir(parents=True, exist_ok=True)
        cache_file = (self._cache / urlname).with_suffix('.safetensors')
        target_file = (target_dir / rename).with_suffix('.safetensors')

        if not cache_file.exists():
            resp = requests.get(url, stream=True)
            total = int(resp.headers.get('content-length', 0))

            try:
                with (
                    cache_file.open('wb') as file,
                    tqdm(
                        desc=cache_file.name,
                        total=total,
                        unit='iB',
                        unit_scale=True,
                        unit_divisor=1024,
                    ) as bar,
                ):
                    for data in resp.iter_content(chunk_size=1024):
                        size = file.write(data)
                        bar.update(size)
            except Exception as e:
                print(f'Url download went wrong: {url}')
                print(e)

        self._symlink(cache_file, target_file)

        item['link'] = str(target_file)
        return item

    def _symlink(self, src: str | Path, target: str | Path, directory=False) -> None:
        src = Path(src)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            os.unlink(str(target))
        os.symlink(str(src), str(target), target_is_directory=directory)

    def _install_item_civitai(self, item: dict) -> dict:
        url = item['config'].get('link', '')
        if not url:
            print('Warning: wget, no link given')
            return {}
        # urlp = urlparse(url)
        # urlpath = Path(urlp.path)
        # urlname = urlpath.name

        target_dir = Path(item['target_dir'])
        target_dir.mkdir(parents=True, exist_ok=True)

        filename_cai = ''

        headers = {
            'Authorization': f'Bearer {self.token_cai}',
            'User-Agent': self.USER_AGENT,
        }

        # Disable automatic redirect handling
        class NoRedirection(urllib.request.HTTPErrorProcessor):
            def http_response(self, request, response):
                return response

            https_response = http_response

        request = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener(NoRedirection)
        response = opener.open(request)

        if response.status in [301, 302, 303, 307, 308]:
            redirect_url = response.getheader('Location')

            # Extract filename from the redirect URL
            parsed_url = urlparse(redirect_url)
            query_params = parse_qs(parsed_url.query)
            content_disposition = query_params.get('response-content-disposition', [None])[0]

            if content_disposition:
                filename_cai = unquote(content_disposition.split('filename=')[1].strip('"'))
            else:
                raise Exception('Unable to determine filename')

            response = urllib.request.urlopen(redirect_url)
        elif response.status == 404:
            raise Exception('File not found')
        else:
            raise Exception('No redirect found, something went wrong')

        total_size = response.getheader('Content-Length')

        if total_size is not None:
            total_size = int(total_size)

        download = False
        cache_file = self._cache / filename_cai
        if not cache_file.exists():
            download = True
        elif total_size > cache_file.stat().st_size:
            download = True
        if item['config'].get('force', False):
            download = True

        if download:
            with cache_file.open('wb') as f:
                downloaded = 0

                while True:
                    chunk_start_time = time.time()
                    buffer = response.read(self.CHUNK_SIZE)
                    chunk_end_time = time.time()
                    speed = 0

                    if not buffer:
                        break

                    downloaded += len(buffer)
                    f.write(buffer)
                    chunk_time = chunk_end_time - chunk_start_time

                    if chunk_time > 0:
                        speed = len(buffer) / chunk_time / (1024**2)  # Speed in MB/s

                    if total_size is not None:
                        progress = downloaded / total_size
                        sys.stdout.write(
                            f'\rDownloading: {filename_cai} [{progress * 100:.2f}%] - {
                                speed:.2f} MB/s'
                        )
            if self.verbose:
                print(f'Download completed. File saved as: {filename_cai}')
        else:
            if self.verbose:
                print('cache ok.')

        target_file = target_dir / filename_cai
        rename = item['config'].get('rename', '')
        if rename:
            target_file = (target_dir / rename).with_suffix('.safetensors')

        self._symlink(cache_file, target_file)

        item['link'] = str(target_file)
        return item

    def _descriptor_item(self, item: dict) -> str:
        descriptor = ''
        repo_id = item['config'].get('repo_id', '')
        file = item['config'].get('file', '')
        link = item['config'].get('link', '')
        rename = item['config'].get('rename', '')

        if repo_id:
            descriptor += repo_id + '/'
        if file:
            descriptor += file
        if link:
            descriptor = link
        if rename:
            descriptor += ' -> ' + rename

        return descriptor
