from typing import Final

import numpy as np
import onnxruntime as rt
import pandas as pd
from PIL import Image

TAGS_CUSTOM: Final = {
    "bodypart": ["body", "pussy", "ass", "breast", "face", "foot", "leg", "mouth", "hand", "thigh", "_step","_penis","+penis", "__tbr"],
    "interaction": ["in", "front", "none", "__tbr"],
    "trigger": ["1gts", "1hairy", "1legs", "1fbb", "__tbr"]
}
TAGS_FOCUS: Final = {
    "realistic": 5469,
    "breasts": 5279,
    "large breasts": 4171,
    "standing": 4099,
    "smile": 4040,
    "thighs": 4013,
    "indoors": 3885,
    "full body": 3681,
    "looking at another": 3526,
    "open mouth": 3386,
    "muscular": 3278,
    "cleavage": 3121,
    "looking at viewer": 3061,
    "makeup": 3039,
    "photorealistic": 3023,
    "medium breasts": 2980,
    "thick thighs": 2692,
    "legs": 2572,
    "lipstick": 2540,
    "simple background": 2531,
    "nude": 2531,
    "high heels": 2489,
    "closed mouth": 2400,
    "parted lips": 2396,
    "sitting": 2393,
    "ass": 2369,
    "fingernails": 2356,
    "mini person": 2293,
    "male focus": 2262,
    "closed eyes": 2235,
    "feet": 2211,
    "teeth": 2087,
    "toes": 2075,
    "barefoot": 2056,
    "miniboy": 2049,
    "nipples": 2038,
    "nail polish": 2010,
    "completely nude": 1853,
    "from below": 1539,
    "holding": 1498,
    "lying": 1488,
    "from behind": 1483,
    "muscular female": 1467,
    "huge breasts": 1466,
    "looking down": 1395,
    "toenails": 1379,
    "pubic hair": 1314,
    "uncensored": 1264,
    "close-up": 1232,
    "penis": 1173,
    "pussy": 1105,
    "biceps": 1101,
    "outdoors": 1085,
    "on back": 1082,
    "female pubic hair": 974,
    "grin": 950,
    "upper body": 930,
    "leg hair": 923,
    "toned": 920,
    "bedroom": 920,
    "stomach": 901,
    "spread legs": 885,
    "on bed": 882,
    "censored": 851,
    "head out of frame": 838,
    "erection": 822,
    "tongue": 821,
    "anus": 816,
    "kneeling": 703,
    "ass focus": 683,
    "testicles": 681,
    "femdom": 624,
    "toenail polish": 616,
    "veiny arms": 615,
    "hairy": 566,
    "thighhighs": 557,
    "clothed female nude male": 552,
    "between breasts": 542,
    "pussy juice": 522,
    "tongue out": 506,
    "excessive pubic hair": 503,
    "looking up": 475,
    "sex": 456,
    "eye contact": 435,
    "armpit hair": 433,
    "on couch": 420,
    "foot focus": 402,
    "clitoris": 397,
    "masturbation": 385,
    "huge ass": 384,
    "lower body": 373,
    "walking": 359,
    "breasts apart": 346,
    "sideboob": 346,
    "armpits": 344,
    "sitting on person": 343,
    "anal hair": 338,
    "on stomach": 337,
    "cum": 331,
    "out of frame": 330,
    "lifting person": 329,
    "stepped on": 328,
    "perspective": 327,
    "vaginal": 323,
    "hands on own hips": 309,
    "carrying": 304,
    "spread pussy": 299,
    "bent over": 269,
    "cunnilingus": 256,
    "girl on top": 255,
    "gigantic breasts": 245,
    "bride": 226,
    "wedding": 226,
    "face to breasts": 226,
    "head between breasts": 223,
    "all fours": 222,
    "saliva": 220,
    "flexing": 218,
    "body hair": 206,
    "female masturbation": 201,
    "grabbing": 194,
    "ass grab": 191,
    "carrying person": 190,
    "licking": 189,
    "on one knee": 189,
    "breast smother": 184,
    "breast focus": 173,
    "anal": 172,
    "groom": 170,
    "ejaculation": 166,
    "fellatio": 158,
    "handjob": 147,
    "male masturbation": 146,
    "breast press": 124,
    "hand focus": 117,
    "pointing": 115,
    "anilingus": 114,
    "kiss": 111,
    "bondage": 89,
    "breast sucking": 87,
    "anus peek": 86,
    "orgasm": 83,
    "footjob": 78,
    "hand on another's thigh": 75,
    "dominatrix": 75,
    "black pubic hair": 74,
    "sex from behind": 59,
    "laughing": 58,
    "breastfeeding": 57,
    "object insertion": 54,
    "handsfree ejaculation": 44,
    "between legs": 41,
    "anal fingering": 30,
    "praying": 30,
    "hands on ass": 30,
    "whip": 27,
    "foot worship": 25,
}
TAGS_AVOID: Final = {
    "1girl": 0,
    "1boy": 0,
    "solo": 4522,
    "solo focus": 3147,
    "muscular male": 2545,
    "multiple boys": 1798,
    "2boys": 1430,
    "manly": 1192,
    "minigirl": 1148,
    "multiple girls": 1072,
    "2girls": 965,
    "statue": 509,
    "blood": 454,
    "horror (theme)": 439,
    "no humans": 427,
    "child": 360,
    "small breasts": 290,
    ":d": 256,
    "baby": 235,
    "fat man": 226,
    "1other": 226,
    "6+boys": 199,
    "incest": 188,
    "mother and son": 187,
    "doll": 159,
    "3boys": 140,
    "genderswap": 131,
    "death": 113,
    "3girls": 95,
    "6+girls": 81,
    "4boys": 67,
    "corpse": 58,
    "character doll": 56,
    "5boys": 47,
    "4girls": 41,
}
# Files to download from the repos
MODEL_FILENAME: Final = "/Volumes/data/Project/AI/REPOS/aitools/build/models/wdtagger/model.onnx"
LABEL_FILENAME: Final = "/Volumes/data/Project/AI/REPOS/aitools/build/models/wdtagger/selected_tags.csv"

# https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
kaomojis = [
    "0_0",
    "(o)_(o)",
    "+_+",
    "+_-",
    "._.",
    "<o>_<o>",
    "<|>_<|>",
    "=_=",
    ">_<",
    "3_3",
    "6_9",
    ">_o",
    "@_@",
    "^_^",
    "o_o",
    "u_u",
    "x_x",
    "|_|",
    "||_||",
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
        self.model_target_size = height

        self.model = model

    def _load_labels(self, dataframe) -> list[str]:
        name_series = dataframe["name"]
        name_series = name_series.map(
            lambda x: x.replace("_", " ") if x not in kaomojis else x
        )
        tag_names = name_series.tolist()

        rating_indexes = list(np.where(dataframe["category"] == 9)[0])
        general_indexes = list(np.where(dataframe["category"] == 0)[0])
        character_indexes = list(np.where(dataframe["category"] == 4)[0])
        return tag_names, rating_indexes, general_indexes, character_indexes

    def _prepare_image(self, image):
        target_size = self.model_target_size

        canvas = Image.new("RGBA", image.size, (255, 255, 255))
        canvas.alpha_composite(image)
        image = canvas.convert("RGB")

        # Pad image to square
        image_shape = image.size
        max_dim = max(image_shape)
        pad_left = (max_dim - image_shape[0]) // 2
        pad_top = (max_dim - image_shape[1]) // 2

        padded_image = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
        padded_image.paste(image, (pad_left, pad_top))

        # Resize
        if max_dim != target_size:
            padded_image = padded_image.resize(
                (target_size, target_size),
                Image.BICUBIC,
            )

        # Convert to numpy array
        image_array = np.asarray(padded_image, dtype=np.float32)

        # Convert PIL-native RGB to BGR
        image_array = image_array[:, :, ::-1]

        return np.expand_dims(image_array, axis=0)

    def tags(
        self,
        image: Image,
        general_thresh = 0.05,
        character_thresh = 0.85,
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
            ", ".join(sorted_general_strings).replace("(", r"\(").replace(")", r"\)")
        )

        return {"tags_sorted": sorted_general_strings, "rating": rating, "tags_wd": general_res}
    
    def tags_prompt(self, tags_raw: dict, thresh: float = 0.3, main_tag: str = "", do_bodypart: bool = False) -> list[str]:
        """
        Creates a list of tags which consist of:
        1. all occuring focus tags in the image tags_sorted (splitted and whitespace removed)
        2. the 20 first tags_sorted but substracted with avoid_tags
        3. the bodypart tags expanded to "interaction with giantess {bodypart}"
        """
        tags_wd = tags_raw.get("tags_wd", {})
        
        # 1. All occurring focus tags
        focus_tags_in_image = []
        for tag in TAGS_FOCUS.keys():
            if tag in tags_wd and tags_wd[tag] > 0: # Check if the tag exists and has a probability > 0
                focus_tags_in_image.append(tag)
        
        # 2. The 7 first tags_sorted but subtracted with avoid_tags
        # tags_sorted is already a comma-separated string, need to split and clean
        sorted_tags_str = tags_raw["tags_sorted"]
        all_sorted_tags = [t.strip() for t in sorted_tags_str.split(',') if t.strip()]
        
        avoid_tags_set = list(TAGS_AVOID.keys())
        if main_tag:
            avoid_tags_set += [main_tag]
        
        # reduce sorted tags by only tags with a probability above a threshold
        # Filter tags_wd by probability > 0.3
        high_prob_tags = [tag for tag, prob in tags_wd.items() if prob > thresh]
        
        # Filter all_sorted_tags to include only those present in high_prob_tags
        # and not in avoid_tags_set, taking the first 20
        filtered_sorted_tags_from_high_prob = []
        for tag in all_sorted_tags:
            if tag in high_prob_tags and tag not in avoid_tags_set:
                filtered_sorted_tags_from_high_prob.append(tag)
            if len(filtered_sorted_tags_from_high_prob) >= 20:
                break
        
        filtered_sorted_tags = []
        for tag in filtered_sorted_tags_from_high_prob:
            if tag not in avoid_tags_set:
                filtered_sorted_tags.append(tag)
            if len(filtered_sorted_tags) >= 20:
                break
        
        # 3. Bodypart tags expanded
        bodypart_tags_expanded = []
        if do_bodypart:
            custom_tags = tags_raw.get("custom", {})
            bodypart_tags = custom_tags.get("bodypart", [])
            for bp_tag in bodypart_tags:
                if bp_tag != "__tbr": # Exclude the "to be removed" tag
                    bodypart_tags_expanded.append(f"interaction with giantess {bp_tag}")

        # Combine all generated tags
        final_tags = []
        final_tags += bodypart_tags_expanded
        final_tags += filtered_sorted_tags
        final_tags += focus_tags_in_image
        
        # Remove duplicates and return
        #ret =  list(set(final_tags))
        return final_tags
        
tagger_wd = TaggerWD()