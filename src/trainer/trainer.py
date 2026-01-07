import os
from pathlib import Path
import shutil
from typing import Final
import threading
import random

from more_itertools import chunked_even

from aidb.hfdataset import HFDatasetImg
from ait.install import AInstaller
from templater import Templater


class Trainer:
    PREFIX: Final = 'train'
    WORKSPACE: Final = Path(os.environ.get('WORKSPACE', '/workspace'))
    HOME_AIT: Final = Path(os.environ.get('HOME_AIT', str(WORKSPACE / '___aitools')))
    ROOT: Final = WORKSPACE / PREFIX

    FILE_TRAIN_SCRIPT: Final = f'{PREFIX}.sh'
    PREFIX_INSTALLER_GROUP: Final = f'{PREFIX}_'
    DIR_DATASET: Final = 'dataset'

    def __init__(
        self,
        model: str,
        repo_ids_hfd: list[str],
        variant: str | None = None,
        config_trainer: dict | None = None,
        config_dataset: dict | None = None,
        multithread: bool = False,
        root: str | None = None,
        trigger: str | None = None,
    ) -> None:
        if root is None:
            self.root = self.ROOT
        else:
            self.root = Path(root)

        self.model = model
        self.variant = variant

        self._config_trainer = {}
        if config_trainer is not None:
            self._config_trainer = config_trainer

        self._config_dataset = {}
        if config_dataset is not None:
            self._config_dataset = config_dataset

        self._installer = AInstaller(self.root, group=self._group_installer, method='diffpipe')
        # print(f'installer vars dataset: {self._installer.vars_bound}')

        self._config_dataset |= {'path': str(self.dir_dataset)}
        self._templater_dataset = Templater(
            'dataset',
            self.model,
            variant=self.variant,
            vars_dict=self.config_dataset,
        )
        self._templater_dataset.save(self.root)

        self._config_trainer |= {'dataset': str(self._templater_dataset.file_saved)}
        self._config_trainer |= self._installer.vars_bound
        print(self.config_trainer)
        self._templater_diffpipe = Templater(
            'diffpipe',
            self.model,
            variant=self.variant,
            vars_dict=self.config_trainer,
        )
        self._templater_diffpipe.save(self.root)

        self._repo_ids_hfd: list[str] = repo_ids_hfd

        self._trigger = trigger

        self._make_dataset(multithread=multithread)
        self._make_file_train_script()

    @property
    def _group_installer(self) -> str:
        group = f'{self.PREFIX_INSTALLER_GROUP}{self.model}'

        if self.variant is not None:
            group += f':{self.variant}'

        return group

    @property
    def config_dataset(self) -> dict:
        return self._config_dataset

    @property
    def config_trainer(self) -> dict:
        return self._config_trainer

    @property
    def dir_dataset(self) -> Path:
        return self.root / self.DIR_DATASET

    def _make_dataset(self, multithread: bool = False) -> None:
        self.dir_dataset.mkdir(parents=True, exist_ok=True)
        for repo_id in self._repo_ids_hfd:
            hfd = HFDatasetImg(repo_id, force_meta_dl=True)
            hfd.cache()
            self._make_dataset_hfd(hfd, multithread=multithread)

    def _make_dataset_hfd(self, hfd: HFDatasetImg, multithread: bool = False) -> None:
        # non multi-threaded
        ids_img = hfd.ids
        if not multithread:
            self._process_imgs(ids_img, hfd)
        else:
            # multi-threaded
            n = 8
            m = len(ids_img)
            ids = []
            for batch in chunked_even(ids_img, (m // n) + 1):
                ids.append(batch)
            if len(ids) != n:
                raise ValueError('dataset multithreading failed!')

            threads = []
            for i in range(n):
                thread = threading.Thread(
                    target=self._process_imgs,
                    args=[
                        ids[i],
                        hfd,
                    ],
                )
                print(f' dataset thread[{i}]: {len(ids[i])} imgs')
                threads.append(thread)
                thread.start()
            for i in range(n):
                threads[i].join()
                print(f' dataset thread[{i}]: joined.')

    def _process_imgs(self, ids: list[str], hfd: HFDatasetImg) -> None:
        max_imgs_to_pick = 50
        if not ids:
            return
        pick_chance = float(max_imgs_to_pick) / float(hfd.size)

        lost = 0
        success = 0
        not_picked = 0
        for id in ids:
            pick = False
            if random.random() < pick_chance:
                pick = True
            if not pick:
                not_picked += 1
                continue
            if not id:
                continue
            idx = hfd.id2idx(id)
            if not idx:
                continue

            # caption or prompt fetch
            prompt = hfd.prompts[idx]
            caption = hfd.captions[idx]
            if not caption:
                caption = prompt
            if not prompt:
                prompt = caption

            if not caption:
                lost += 1
                print(f'caption missing for {id}!')
                continue

            # TODO more generic, and take care that the dataset isnt polluted with trigger words
            caption = caption.replace('1gts,', '')
            caption = caption.replace('1woman,', '')

            if self._trigger is not None:
                caption = f'{self._trigger},' + caption

            # img file
            try:
                img_file_dl = hfd.img_download(idx)
            except Exception as e:
                lost += 1
                print(f'{e}\n{id} not downloadable!')
                continue

            # copy file to dataset folder
            img_file = self.dir_dataset / img_file_dl.name
            shutil.copy(str(img_file_dl), str(img_file))

            # write caption to file
            cap_file = img_file.with_suffix('.txt')
            with cap_file.open('w', encoding='utf-8') as f:
                f.write(caption)

            # ok
            success += 1
        print(
            f'dataset thread finished: {success} successes, {lost} losses, {not_picked} not picked'
        )

    def _make_file_train_script(self) -> None:
        str_file = f"""
NCCL_P2P_DISABLE="1" NCCL_IB_DISABLE="1" deepspeed --num_gpus=1 train.py --deepspeed --config {self._templater_diffpipe.file_saved}
"""
        file_train = self.root / self.FILE_TRAIN_SCRIPT
        # save train string to train script and chmod 777 it.
        with file_train.open('w', encoding='utf-8') as f:
            f.write(str_file)
        file_train.chmod(0o777)


#    #
#    # wan22_high diffpipe config
#    #
#    def _make_file_diffpipe_config_wan22_high(self) -> None:
#        str_file = f"""
# [model]
# type = 'wan'
## this is the config checkout for the checkpoint but w/o the specific model
# ckpt_path = 'self._model_links['base']'
## this is the used checkpoint model (compatible with the base checkpoint config!)
# transformer_path = 'self._model_links['ckpt']'
## this is the used text encoder model (compatible with the base checkpoint config!)
# llm_path = 'self._model_links['text_encoder']'
# dtype = 'bfloat16'
# transformer_dtype = 'float8'
# timestep_sample_method = 'logit_normal'
# min_t = 0.875
# max_t = 1
# """
#
#    #
#    # wan22_low diffpipe config
#    #
#    def _make_file_diffpipe_config_wan22_low(self) -> None:
#        str_file = f"""
# [model]
# type = 'wan'
## this is the config checkout for the checkpoint but w/o the specific model
# ckpt_path = 'self._model_links['base']'
## this is the used checkpoint model (compatible with the base checkpoint config!)
# transformer_path = 'self._model_links['ckpt']'
## this is the used text encoder model (compatible with the base checkpoint config!)
# llm_path = 'self._model_links['text_encoder']'
# min_t = 0.0
# max_t = 0.875
# [optimizer]
# lr = 2.0 * self._lr
# betas = [0.9, 0.99]
# weight_decay = 0.01
# eps = 1e-8
# """
#
#    #
#    # qwen-image diffpipe config
#    #
#    def _make_file_diffpipe_config_qwen_image(self) -> None:
#        str_file = f"""
# [model]
# type = 'qwen_image'
## this is the config checkout for the checkpoint but w/o the specific model
# diffusers_path = 'self._model_links['base']'
## this is the used checkpoint model (compatible with the base checkpoint config!)
# transformer_path = 'self._model_links['ckpt']'
## this is the used text encoder model (compatible with the base checkpoint config!)
##text_encoder_path = 'self._model_links['text_encoder']'
# """
