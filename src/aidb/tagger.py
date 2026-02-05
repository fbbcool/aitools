from typing import Final

import numpy as np
import onnxruntime as rt
import pandas as pd
from PIL import Image

from .tagger_defines import TaggerDef

# Files to download from the repos
MODEL_FILENAME: Final = '/home/misw/venv/aitools/aitools/build/wdtagger/model.onnx'
LABEL_FILENAME: Final = '/home/misw/venv/aitools/aitools/build/wdtagger/selected_tags.csv'

# https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
kaomojis = [
    '0_0',
    '(o)_(o)',
    '+_+',
    '+_-',
    '._.',
    '<o>_<o>',
    '<|>_<|>',
    '=_=',
    '>_<',
    '3_3',
    '6_9',
    '>_o',
    '@_@',
    '^_^',
    'o_o',
    'u_u',
    'x_x',
    '|_|',
    '||_||',
]


class TaggerWD:
    def __init__(self):
        self.model_target_size = None
        self.model = None
        self._load_model()

    def _load_model(self):
        csv_path = LABEL_FILENAME
        model_path = MODEL_FILENAME

        tags_df = pd.read_csv(csv_path)
        sep_tags = self._load_labels(tags_df)

        self.tag_names = sep_tags[0]
        self.rating_indexes = sep_tags[1]
        self.general_indexes = sep_tags[2]
        self.character_indexes = sep_tags[3]

        del self.model
        model = rt.InferenceSession(model_path)
        _, height, width, _ = model.get_inputs()[0].shape
        self.model_target_size = int(height)

        self.model = model

    def _load_labels(self, dataframe):
        name_series = dataframe['name']
        name_series = name_series.map(lambda x: x.replace('_', ' ') if x not in kaomojis else x)
        tag_names = name_series.tolist()

        rating_indexes = list(np.where(dataframe['category'] == 9)[0])
        general_indexes = list(np.where(dataframe['category'] == 0)[0])
        character_indexes = list(np.where(dataframe['category'] == 4)[0])
        return tag_names, rating_indexes, general_indexes, character_indexes

    def _prepare_image(self, image):
        target_size = self.model_target_size

        canvas = Image.new('RGBA', image.size, (255, 255, 255))
        canvas.alpha_composite(image)
        image = canvas.convert('RGB')

        # Pad image to square
        image_shape = image.size
        max_dim = max(image_shape)
        pad_left = (max_dim - image_shape[0]) // 2
        pad_top = (max_dim - image_shape[1]) // 2

        padded_image = Image.new('RGB', (max_dim, max_dim), (255, 255, 255))
        padded_image.paste(image, (pad_left, pad_top))

        # Resize
        if max_dim != target_size:
            padded_image = padded_image.resize((target_size, target_size), Image.Resampling.LANCZOS)

        # Convert to numpy array
        image_array = np.asarray(padded_image, dtype=np.float32)

        # Convert PIL-native RGB to BGR
        image_array = image_array[:, :, ::-1]

        return np.expand_dims(image_array, axis=0)

    def tags(
        self,
        image: Image.Image,
        general_thresh=0.05,
        character_thresh=0.85,
    ):
        image = self._prepare_image(image.convert('RGBA'))

        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        preds = self.model.run([label_name], {input_name: image})[0]

        labels = list(zip(self.tag_names, preds[0].astype(float)))

        # First 4 labels are actually ratings: pick one with argmax
        ratings_names = [labels[i] for i in self.rating_indexes]
        rating = dict(ratings_names)

        # Then we have general tags: pick any where prediction confidence > threshold
        general_names = [labels[i] for i in self.general_indexes]

        general_res = [x for x in general_names if x[1] > general_thresh]
        general_res = dict(general_res)

        # Everything else is characters: pick any where prediction confidence > threshold
        character_names = [labels[i] for i in self.character_indexes]

        character_res = [x for x in character_names if x[1] > character_thresh]
        character_res = dict(character_res)

        sorted_general_strings = sorted(
            general_res.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        sorted_general_strings = [x[0] for x in sorted_general_strings]
        sorted_general_strings = (
            ', '.join(sorted_general_strings).replace('(', r'\(').replace(')', r'\)')
        )

        return {'tags_sorted': sorted_general_strings, 'rating': rating, 'tags_wd': general_res}

    def tags_prompt(
        self,
        tags_raw: dict,
        thresh: float = 0.3,
        trigger: str = '',
        max_tags: int = 30,
        do_bodypart: bool = False,
    ) -> list[str]:
        """
        Creates a list of tags which consist of:
        1. all occuring focus tags in the image tags_sorted (splitted and whitespace removed)
        2. the 20 first tags_sorted but substracted with avoid_tags
        3. the bodypart tags expanded to "interaction with giantess {bodypart}"
        """
        tags_wd = tags_raw.get('tags_wd', {})

        # 1. All occurring focus tags
        focus_tags_in_image = []
        for tag in TaggerDef.TAGS_FOCUS.keys():
            if (
                tag in tags_wd and tags_wd[tag] > 0
            ):  # Check if the tag exists and has a probability > 0
                focus_tags_in_image.append(tag)

        # 2. The 7 first tags_sorted but subtracted with avoid_tags
        # tags_sorted is already a comma-separated string, need to split and clean
        sorted_tags_str = tags_raw['tags_sorted']
        all_sorted_tags = [t.strip() for t in sorted_tags_str.split(',') if t.strip()]

        avoid_tags_set = list(TaggerDef.TAGS_AVOID.keys())
        if trigger == '1penis':
            avoid_tags_set += ['penis', 'erection', 'testicles']
        if trigger == '1gts':
            avoid_tags_set += TaggerDef.TAGS_AVOID_1GTS

        # reduce sorted tags by only tags with a probability above a threshold
        # Filter tags_wd by probability > 0.3
        high_prob_tags = [tag for tag, prob in tags_wd.items() if prob > thresh]

        # Filter all_sorted_tags to include only those present in high_prob_tags
        # and not in avoid_tags_set, taking the first 20
        ret = [tag for tag in focus_tags_in_image if tag not in avoid_tags_set]
        for tag in all_sorted_tags:
            pass
            if tag in avoid_tags_set:
                continue
            if tag in focus_tags_in_image:
                continue
            if tag in high_prob_tags:
                ret.append(tag)
            if len(ret) >= max_tags:
                break

        # 3. Bodypart tags expanded
        bodypart_tags_expanded = []
        if do_bodypart:
            custom_tags = tags_raw.get('custom', {})
            bodypart_tags = custom_tags.get('bodypart', [])
            for bp_tag in bodypart_tags:
                if bp_tag != '__tbr':  # Exclude the "to be removed" tag
                    bodypart_tags_expanded.append(f'interaction with giantess {bp_tag}')
            ret = bodypart_tags_expanded + ret

        # Remove duplicates and return
        # ret =  list(set(ret))
        return ret


tagger_wd = TaggerWD()
