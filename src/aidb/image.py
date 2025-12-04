import json
from pathlib import Path
from typing import List, Dict, Literal, Optional, Union, Any, Tuple
from bson.objectid import ObjectId
from PIL import Image as PILImage
import numpy as np  # Import Image from Pillow and alias it to avoid conflict with our class name

from aidb.dbdefines import TAGS_TRIGGER
from aidb.dbmanager import DBManager  # Updated import
from aidb.hfdataset import HFDatasetImg
from aidb.tagger import tagger_wd as tagger  # Updated import


class Image:
    """
    A class to manage and update metadata for a single image document
    in the MongoDB database.
    """

    def __init__(
        self,
        db_manager: DBManager,
        image_id: str,
        collection: str | None = None,
        doc: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initializes the Image object with a reference to the DBManager
        and the MongoDB _id of the image.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
            image_id (str): The string representation of the MongoDB '_id' for this image.
            doc (Optional[Dict[str, Any]]): An optional pre-fetched document from the database.
                                             If provided, it prevents an extra database call.
            collection: DB collection which hosts the image data. it can be pulled from the current db manager collection or set directly. the user has to take care of correctness!
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError('db_manager must be an instance of DBManager.')

        # Validate if image_id is a valid ObjectId string
        try:
            ObjectId(image_id)
        except Exception:
            raise ValueError(
                f"Invalid image_id format: '{image_id}'. Must be a valid MongoDB ObjectId string."
            )

        self._db_manager = db_manager
        self._image_id = image_id
        self._data = doc  # Store the pre-fetched document
        self.score = 0.0
        self.contributing_tags = []
        self.operation: Literal['nop', 'rate', 'scene'] = 'nop'
        self._caption: str | None = None
        self._prompt: str | None = None
        if collection is None:
            self._collection = self._db_manager._collection
        else:
            self._collection = collection
        self._hfd_repo_id = None
        self._hfd = None

    @property
    def id(self) -> str:
        """Returns the MongoDB _id of this image."""
        return self._image_id

    @property
    def collection(self):
        """Returns the MongoDB collection of this image."""
        return self._collection

    @property
    def search_collection(self) -> list[str]:
        """
        Searches all image collections and returns all collections which contain this image id.
        """
        collections = self._db_manager.collections_images
        found_collections = []
        for collection_name in collections:
            # Check if the image ID exists in this collection
            if self._db_manager.find_documents(collection_name, {'_id': ObjectId(self._image_id)}):
                found_collections.append(collection_name)
        return found_collections

    @property
    def container(self) -> str | None:
        """Returns the container of this image."""
        container_id = self.data.get('container_id', None)
        if container_id is None:
            return None
        return self._db_manager.name_container(container_id)

    @property
    def container_url_relative(self) -> str:
        """
        Returns the relative path of the image container relative to the pool directory in the
        container local path without the poll directory itself.
        """
        pool_dir = 'pool'
        container_local_path_str = self.data.get('container_local_path')
        if container_local_path_str is None:
            return ''

        # Find the position of "pool" in the path
        try:
            pool_index = container_local_path_str.find(pool_dir)
            if pool_index != -1:
                # Extract the part of the path after "pool/"
                relative_path_start_index = pool_index + len(pool_dir) + 1  # +1 for the slash
                return container_local_path_str[relative_path_start_index:]
        except Exception as e:
            print(f'Error parsing container_local_path: {e}')
        return ''

    @property
    def data(self) -> dict:
        """
        Fetches and caches the image's metadata from the database.
        """
        if self._data is not None:
            return self._data

        # Fetch the image document from the database
        image_doc = self._db_manager.find_documents(
            self._collection, {'_id': ObjectId(self._image_id)}
        )

        if not image_doc:
            print(f"Error: Image with ID '{self._image_id}' not found in the database.")
            collections = self.search_collection
            if not collections:
                self._data = {}
                return self._data
            self._collection = collections[0]
            image_doc = self._db_manager.find_documents(
                self._collection, {'_id': ObjectId(self._image_id)}
            )

        # Assuming find_documents returns a list, take the first one
        self._data = image_doc[0]
        return self._data

    @property
    def tags(self) -> dict:
        """Returns the tags dictionary from the image data."""
        if self.data is None:
            return {}
        # Use .get to safely access, return empty dict if 'tags' is missing
        return self.data.get('tags', {})

    def tags_prompt(self, trigger: str = '') -> list[str]:
        return tagger.tags_prompt(self.tags, trigger=trigger)

    @property
    def rating(self) -> int | None:
        """Returns the rating of the image."""
        if self.data is None:
            return None
        return self.data.get('rating')

    @property
    def hfd_repo_id(self) -> str | None:
        if self._hfd_repo_id is None:
            # _get tries it once! if it fails, it return an emtpy string to avoid second tries!
            self._hfd_repo_id = self.data.get('hfd_repo_id', '')
            if not self._hfd_repo_id:
                self._hfd_repo_id = self._db_manager.get_collection_hfd(self._collection)
            if self._hfd_repo_id is None:
                self._hfd_repo_id = ''
            # now determinig really failed and set it to empty to avoid subsequent tries!

        elif not self._hfd_repo_id:
            return None

        return self._hfd_repo_id

    @property
    def hfd(self) -> HFDatasetImg | None:
        repo_id = self.hfd_repo_id
        if repo_id is None:
            return None
        return self._db_manager.get_hfd(self.hfd_repo_id)

    @property
    def caption(self) -> str | None:
        if self._caption is None:
            caption_new = self._hfd_caption_search
            if caption_new is None:
                self._caption = ''
            else:
                self._caption = caption_new

        # always return None, regardless of None or empty.
        if not self._caption:
            return None
        return self._caption

    @property
    def _hfd_caption_joy(self) -> str | None:
        _hfd = self.hfd
        if _hfd is None:
            return None

        idx = _hfd.id2idx(self.id)
        if idx is not None:
            return _hfd.captions_joy[idx]
        return None

    @property
    def _hfd_caption(self) -> str | None:
        _hfd = self.hfd
        if _hfd is None:
            return None

        idx = _hfd.id2idx(self.id)
        if idx is not None:
            return _hfd.captions[idx]
        return None

    @property
    def _hfd_caption_search(self) -> str | None:
        _hfd = self.hfd
        if _hfd is None:
            return None
        caption = self._hfd_caption
        if caption is None:
            for _hfd in self._db_manager.hfds:
                idx = _hfd.id2idx(self.id)  # pyright: ignore
                if idx is None:
                    continue
                caption = _hfd.captions[idx]  # pyright: ignore
                if caption:
                    break
        return caption

    @property
    def prompt(self) -> str | None:
        if self._prompt is None:
            prompt = self._prompt_meta
            if prompt is None:
                self._prompt = ''
            else:
                self._prompt = prompt
        if not self._prompt:
            return None
        return self._prompt

    @property
    def _prompt_meta(self) -> str | None:
        prompt = None
        try:
            pil = self.pil
            if pil is None:
                return None
            pil.load()  # necessary after .open() for metadata!
            data = json.loads(pil.info['prompt'])
            ksampler = {}
            for id in data:
                class_type = data[id]['class_type']
                if class_type in ['KSampler', 'WanVideoSampler', 'WanMoeKSampler']:
                    ksampler = data[id]
                    break
            inputs = ksampler.get('inputs', None)
            if inputs is None:
                return None

            prompt = None
            value = None
            for key in ['positive', 'text_embeds']:
                value = inputs.get(key, None)
                if value is not None:
                    id_pos = value[0]
                    prompt = data[id_pos]
                    break  # of for

            max_loop = 10
            while not isinstance(prompt, str):
                if prompt is None:
                    return None

                max_loop -= 1
                if max_loop < 0:
                    prompt = None
                    return None

                inputs = None
                if isinstance(prompt, list):
                    id_pos = prompt[0]
                    node_pos = data[id_pos]
                    if isinstance(node_pos, dict):
                        inputs = node_pos.get('inputs', None)
                elif isinstance(prompt, dict):
                    inputs = prompt.get('inputs', None)
                else:
                    return None

                if inputs is None:
                    return None

                prompt = inputs.get('text', None)
                for key in ['Text', 'string_b', 'positive_prompt']:
                    value = inputs.get(key, None)
                    if value is not None:
                        prompt = value
                        break  # for

        except Exception:
            return None

        # always return None, regardless of None or empty.
        if not prompt:
            return None
        if isinstance(prompt, str):
            for trigger in TAGS_TRIGGER:
                prompt = prompt.replace(f'{trigger},', '')
        else:
            return None
        return prompt

    def set_rating(self, rating: int) -> int:
        """Sets the rating of the image."""
        if not (-2 <= rating <= 5):
            raise ValueError('Rating must be between -2 and 5.')
        print(f'Setting rating for image {self._image_id} to {rating}')
        return self._db_manager.update_image(self._image_id, rating=rating)

    def get_tags_custom(self, category: str) -> list[str]:
        """Returns tags of a custom category."""
        tags = self.tags
        if 'custom' in tags:
            custom_tags = tags['custom']
        else:
            return []
        if category in custom_tags:
            return custom_tags[category]
        else:
            return []

    def set_tags_custom(self, category: str, tags_category: list[str]) -> int:
        """Sets custom category tags"""
        tags = self.tags
        tags_custom = tags['custom'] if 'custom' in tags else {}
        tags_custom[category] = tags_category
        return self.update_tags({'custom': tags_custom})

    def generate_tags(self) -> dict:
        """
        Generates tags for the image using the configured tagger.
        Requires the PIL image to be loadable.
        """
        if self.pil:
            return tagger.tags(self.pil)
        else:
            print(
                f'Warning: Cannot generate tags for image {
                    self._image_id
                } as PIL image could not be loaded.'
            )
            return {}

    def get_full_path(self) -> Optional[Path]:
        """
        Retrieves the full local file system path of the image.

        This method fetches the image's metadata from the database to
        construct the full path using 'container_local_path' and 'relative_url'.

        Returns:
            Optional[pathlib.Path]: A pathlib.Path object representing the full
                                    local path, or None if the image metadata
                                    or path components are not found.
        """
        if self.data is None:
            print(f"Cannot get full path: Image data not available for ID '{self._image_id}'.")
            return None

        try:
            full_path = (
                Path(self._db_manager._root)
                / self.container_url_relative
                / self.data.get('relative_url')
            )
            return full_path
        except Exception as e:
            print(f"Error constructing full path for image ID '{self._image_id}': {e}")
            return None

    @property
    def pil(self) -> PILImage.Image | None:
        """
        Retrieves the image as a PIL (Pillow) Image object.

        This method first gets the full local path of the image and then
        attempts to open it using Pillow.

        Returns:
            Optional[PILImage.Image]: A PIL Image object, or None if the image
                                      file cannot be found or opened.
        """
        full_path = self.get_full_path()
        if full_path is None:
            print(f"Cannot get PIL image: Full path not available for image ID '{self._image_id}'.")
            return None

        if not full_path.exists():
            print(
                f"Warning: Image file not found at '{full_path}' for image ID '{self._image_id}'."
            )
            for res in [1024, 768]:
                new_path = self.path_train_image_from_dbm_and_res(res)
                if new_path.exists():
                    print(f"Ok, using train image {res} instead for image ID '{self._image_id}'.")
                    full_path = new_path
                    break

        try:
            pil_image = PILImage.open(full_path)
            # print(f"Successfully opened image '{full_path}' as PIL image.") # Too verbose
            return pil_image
        except FileNotFoundError:
            print(f"Error: Image file not found at '{full_path}'.")
            return None
        except IOError as e:
            print(f"Error opening image file '{full_path}': {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred while getting PIL image for '{full_path}': {e}")
            return None

    @property
    def thumbnail_path(self) -> Path:
        thumbnail_filename = f'{self._image_id}_thumb.png'
        thumbnail_path = (
            Path(self._db_manager._root)
            / self._db_manager._default_thumbnail_dir
            / thumbnail_filename
        )
        return thumbnail_path

    @property
    def thumbnail(self) -> Optional[PILImage.Image]:
        """
        Retrieves the thumbnail image as a PIL (Pillow) Image object.
        If a thumbnail URL exists in the database and the file exists, it loads it.
        Otherwise, it generates a new thumbnail, saves it, updates the database,
        and then loads and returns the newly created thumbnail.
        """
        thumbnail_path = self.thumbnail_path
        if thumbnail_path.exists():
            try:
                thumb_pil_image = PILImage.open(thumbnail_path)
                # print(f"Successfully loaded existing thumbnail for ID '{self._image_id}'.")
                return thumb_pil_image
            except Exception as e:
                print(
                    f"Warning: Could not load existing thumbnail '{thumbnail_path}' for ID '{
                        self._image_id
                    }': {e}. Attempting to regenerate."
                )

        # 2. If not found or failed to load, generate and save a new one
        print(f"Generating new thumbnail for image ID '{self._image_id}'.")
        self.thumbnail_create(thumbnail_path)
        if thumbnail_path.exists():
            try:
                thumb_pil_image = PILImage.open(thumbnail_path)
                # print(f"Successfully loaded existing thumbnail for ID '{self._image_id}'.")
                return thumb_pil_image
            except Exception as e:
                print(
                    f"Warning: Could not load existing thumbnail '{thumbnail_path}' for ID '{
                        self._image_id
                    }': {e}. Regeneration failed!"
                )
                return None

    @property
    def train_image(self) -> Optional[PILImage.Image]:
        """
        Retrieves the training image as a PIL (Pillow) Image object.
        If a training image URL exists in the database and the file exists, it loads it.
        Otherwise, it generates a new training image, saves it, updates the database,
        and then loads and returns the newly created training image.
        """
        if self.data is None:
            print(f"Cannot get training image: Image data not available for ID '{self._image_id}'.")
            return None

        train_image_url_str = self.url_train_image

        # Get training image settings from DBManager's properties
        output_train_image_dir = self._db_manager.default_train_image_dir
        output_train_image_size = self._db_manager.default_train_image_size

        # 1. Check if training image URL exists and file exists on disk
        if train_image_url_str:
            train_image_path = Path(train_image_url_str)
            if train_image_path.exists():
                try:
                    train_pil_image = PILImage.open(train_image_path)
                    # print(f"Successfully loaded existing training image for ID '{self._image_id}'.")
                    return train_pil_image
                except Exception as e:
                    print(
                        f"Warning: Could not load existing training image '{
                            train_image_path
                        }' for ID '{self._image_id}': {e}. Attempting to regenerate."
                    )

        # 2. If not found or failed to load, generate and save a new one
        print(f"Generating new training image for image ID '{self._image_id}'.")
        created_train_image_path = self.save_train_image_and_update_db(
            output_directory=output_train_image_dir,
            train_image_size=output_train_image_size,
        )

        if created_train_image_path:
            try:
                # Load the newly created training image
                new_train_pil_image = PILImage.open(created_train_image_path)
                print(
                    f"Successfully loaded newly generated training image for ID '{self._image_id}'."
                )
                return new_train_pil_image
            except Exception as e:
                print(
                    f"Error loading newly created training image '{
                        created_train_image_path
                    }' for ID '{self._image_id}': {e}"
                )
                return None
        else:
            print(f"Failed to create or save training image for image ID '{self._image_id}'.")
            return None

    @property
    def url_train_image(self) -> str:
        return str(self.path_train_image_from_dbm)

    @property
    def path_train_image_from_dbm(self) -> Path:
        """
        Returns the URL of the training image from constructing with dbm config
        """
        output_train_image_size = self._db_manager.default_train_image_size
        return self.path_train_image_from_dbm_and_res(output_train_image_size[0])

    def path_train_image_from_dbm_and_res(self, res: int) -> Path:
        path_train_imgs = Path(self._db_manager.default_train_image_dir)
        name_train_img = f'{self._image_id}_{res}'
        path_train_img = (path_train_imgs / name_train_img).with_suffix('.png')
        return path_train_img

    @property
    def url_train_image_from_data(self) -> str | None:
        """
        Returns the URL of the training image store in the image meta data.
        """
        if self.data is None:
            return None
        return self.data.get('train_image_url')

    @property
    def statistics(self) -> dict:
        """
        Returns the statistics section of the metadata.

        If no statistics are available, it returns an empty dictionary.
        """
        if self.data is None:
            return {}
        return self.data.get('statistics', {})

    @property
    def focus_vector(self) -> np.ndarray | None:
        """
        Returns the focus vector  from the statistics of the image as an np.ndarray.

        If no focus vector is available, it returns None.
        """
        if self.statistics is None:
            return None

        focus_vector_list = self.statistics.get('focus_vector')
        if focus_vector_list is None:
            return None

        return np.array(focus_vector_list)

    @property
    def neighbors(self) -> dict[str, float]:
        """
        Returns the neighbors dictionary from the metadata.

        If no neighbors are available, it returns an empty dictionary.
        """
        if self.statistics is None:
            return {}
        return self.statistics.get('neighbors', {})

    @property
    def neighbor0(self) -> tuple[str, float] | None:
        """Returns the nearest neighbor"""
        neighbors = self.neighbors
        if not neighbors:
            return None

        # Neighbors are already sorted by distance (lowest first)
        # Get the first item (key, value) from the dictionary
        first_neighbor_id = next(iter(neighbors))
        first_neighbor_distance = neighbors[first_neighbor_id]
        return (first_neighbor_id, first_neighbor_distance)

    def get_other_by_id(self, iid: str):
        return Image(self._db_manager, iid)

    def save_png_image(
        self,
        output_path: Union[str, Path],
        compression: int = 6,
        size: Optional[Tuple[int, int]] = None,
    ) -> Optional[Path]:
        """
        Saves the image as a PNG file to the specified output path.
        The filename will be the image's MongoDB _id with a .png extension.
        Optionally resizes the image to exact dimensions and applies compression.

        Args:
            output_path (Union[str, pathlib.Path]): The directory where the PNG image should be saved.
            compression (int): PNG compression level (0-9, where 0 is no compression, 9 is max compression).
                               Defaults to 6.
            size (Optional[Tuple[int, int]]): A tuple (width, height) specifying the exact dimensions
                                               the image should be resized to. If None, no resizing occurs.

        Returns:
            Optional[pathlib.Path]: The full path to the saved PNG image, or None on failure.
        """
        pil_image = self.pil
        if pil_image is None:
            print(f"Failed to get PIL image for saving PNG for ID '{self._image_id}'.")
            return None

        output_dir_path = Path(output_path)
        output_dir_path.mkdir(parents=True, exist_ok=True)  # Ensure output directory exists

        output_filename = f'{self._image_id}.png'
        full_output_path = output_dir_path / output_filename

        try:
            # Handle resizing if size is specified
            if size is not None:
                if not (
                    isinstance(size, tuple)
                    and len(size) == 2
                    and all(isinstance(dim, int) and dim > 0 for dim in size)
                ):
                    print(
                        f"Error: 'size' must be a tuple of two positive integers (width, height). Got {
                            size
                        }"
                    )
                    return None

                # Create a copy to resize, keeping original PIL image intact if needed elsewhere
                resized_pil_image = pil_image.copy()
                resized_pil_image.resize((size[0], size[1]), PILImage.Resampling.LANCZOS)
                pil_image_to_save = resized_pil_image
                print(f"Image '{self._image_id}' resized to {size[0]}x{size[1]}.")
            else:
                pil_image_to_save = pil_image

            # Save the image with specified compression
            pil_image_to_save.save(
                full_output_path, 'PNG', optimize=True, compress_level=compression
            )
            print(
                f"Image '{self._image_id}' saved successfully to '{
                    full_output_path
                }' with compression level {compression}."
            )
            return full_output_path
        except Exception as e:
            print(f"Error saving PNG image '{self._image_id}' to '{full_output_path}': {e}")
            return None

    def thumbnail_create(self, to_path: Path) -> None:
        """
        Generates a thumbnail for the image, saves it as a PNG in the specified path.
        """
        pil_image = self.pil
        if pil_image is None:
            print(f"Failed to get PIL image for thumbnail generation for ID '{self._image_id}'.")
            return None

        try:
            # Create a copy to ensure the original PIL image object is not modified
            thumb_pil_image = pil_image.copy()
            thumb_pil_image.thumbnail(
                self._db_manager._default_thumbnail_size, PILImage.Resampling.LANCZOS
            )  # Preserves aspect ratio

            thumb_pil_image.save(to_path, 'PNG', optimize=True, compress_level=6)
            print(f"Thumbnail for image '{self._image_id}' saved to '{to_path}'.")

        except Exception as e:
            print(f"Error generating or saving thumbnail for image '{self._image_id}': {e}")
            return None

    def save_train_image_and_update_db(
        self,
        output_directory: Union[str, Path],
        train_image_size: Tuple[int, int] = (128, 128),
    ) -> Optional[str]:
        """
        Generates a training image for the image, saves it as a PNG in the specified directory,
        and updates the 'train_image_url' field in the database.
        """
        pil_image = self.pil
        if pil_image is None:
            print(f"Failed to get PIL image for thumbnail generation for ID '{self._image_id}'.")
            return None

        output_dir_path = Path(output_directory)
        output_dir_path.mkdir(parents=True, exist_ok=True)  # Ensure output directory exists

        train_img_filename = f'{self._image_id}_{train_image_size[0]}.png'
        full_train_img_path = output_dir_path / train_img_filename

        if full_train_img_path.exists():
            print(
                f"Train image for image '{self._image_id}' already exists at '{
                    full_train_img_path
                }'."
            )
            return str(full_train_img_path)

        try:
            # Create a copy to ensure the original PIL image object is not modified
            train_pil_image = pil_image.copy()
            # Rescale longest edge to size, upscaling if necessary
            width, height = train_pil_image.size
            # if size is already ok, just copy the image
            if width == train_image_size[0] or height == train_image_size[1]:
                # No resizing needed
                pass
            elif width > height:
                # Landscape or square
                new_width = train_image_size[0]
                new_height = int(new_width * height / width) if width > 0 else 0
                train_pil_image = train_pil_image.resize(
                    (new_width, new_height), PILImage.Resampling.LANCZOS
                )
            else:
                # Portrait
                new_height = train_image_size[1]
                new_width = int(new_height * width / height) if height > 0 else 0
                train_pil_image = train_pil_image.resize(
                    (new_width, new_height), PILImage.Resampling.LANCZOS
                )

            train_pil_image.save(full_train_img_path, 'PNG', optimize=True, compress_level=6)
            print(f"Train image for image '{self._image_id}' saved to '{full_train_img_path}'.")

            # Update the database with the new thumbnail URL
            # For simplicity, we'll store the local file path as the URL.
            # In a web application, this might be a URL to a served static file.
            updated_count = self._db_manager.update_image(
                self._image_id, train_image_url=str(full_train_img_path)
            )

            if updated_count and updated_count > 0:
                print(f"Train image URL updated in DB for image '{self._image_id}'.")
                # Clear cached data so next .data access fetches updated thumbnail_url
                self._data = None
                return str(full_train_img_path)
            else:
                print(f"Failed to update thumbnail URL in DB for image '{self._image_id}'.")
                return None

        except Exception as e:
            print(f"Error generating or saving thumbnail for image '{self._image_id}': {e}")
            return None

    def update_description(self, description: List[Dict[str, str]]) -> Optional[int]:
        """Updates the description field of the image."""
        print(f'Updating description for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, description=description)

    def update_creation_date(self, creation_date: str) -> Optional[int]:
        """Updates the creation_date field of the image."""
        print(f'Updating creation_date for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, creation_date=creation_date)

    def update_last_modified_date(self, last_modified_date: str) -> Optional[int]:
        """Updates the last_modified_date field of the image."""
        print(f'Updating last_modified_date for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, last_modified_date=last_modified_date)

    def update_tags(self, tags: List[Dict[str, Any]]) -> Optional[int]:
        """Updates the tags field of the image."""
        print(f'Updating tags for image {self._image_id}')
        new_tags = self.tags
        new_tags |= tags
        return self._db_manager.update_image(self._image_id, tags=new_tags)

    def init_tags(self, force: bool = False) -> Optional[int]:
        """Initializes the tags field of the image."""
        ret = 0
        if not self.tags or force:
            ret = self._db_manager.update_image(self._image_id, tags=self.generate_tags())
        return ret

    def update_dimensions(self, dimensions: Dict[str, Union[int, str]]) -> Optional[int]:
        """Updates the dimensions field of the image."""
        print(f'Updating dimensions for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, dimensions=dimensions)

    def update_thumbnail_url(self, thumbnail_url: str) -> Optional[int]:
        """Updates the thumbnail_url field of the image."""
        print(f'Updating thumbnail_url for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, thumbnail_url=thumbnail_url)

    def update_rating(self, rating: int) -> Optional[int]:
        """Updates the rating field of the image."""
        print(f'Updating rating for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, rating=rating)

    def update_category(self, category: str) -> Optional[int]:
        """Updates the category field of the image."""
        print(f'Updating category for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, category=category)

    def update_container_db_id(self, container_db_id: str) -> Optional[int]:
        """Updates the container_db_id field of the image."""
        print(f'Updating container_db_id for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, container_db_id=container_db_id)

    def update_collection(self, collection: str) -> Optional[int]:
        """Updates the collection field of the image."""
        print(f'Updating collection for image {self._image_id}')
        return self._db_manager.update_image(self._image_id, collection=collection)

    def update_all(
        self,
        description: Optional[List[Dict[str, str]]] = None,
        creation_date: Optional[str] = None,
        last_modified_date: Optional[str] = None,
        tags: Optional[List[Dict[str, Any]]] = None,
        dimensions: Optional[Dict[str, Union[int, str]]] = None,
        thumbnail_url: Optional[str] = None,
        rating: Optional[int] = None,
        category: Optional[str] = None,
        container_db_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Updates multiple fields of the image document.
        Any parameter left as None will not be updated.
        """
        print(f'Updating multiple fields for image {self._image_id}')
        return self._db_manager.update_image(
            self._image_id,
            description=description,
            creation_date=creation_date,
            last_modified_date=last_modified_date,
            tags=tags,
            dimensions=dimensions,
            thumbnail_url=thumbnail_url,
            rating=rating,
            category=category,
            container_db_id=container_db_id,
        )

    def match_tags(self, tags: list[str]) -> float:
        """
        Calculates a score based on the sum of probabilities of given tags.
        """
        ret = 0.0
        for tag in tags:
            ret += self.get_tag_probability(tag)
        return ret

    def get_tag_probability(self, tag: str) -> float:
        """
        Returns the probability of a specific tag from the 'tags_wd' dictionary.
        Returns 0.0 if the tag is not found.
        """
        if self.data is None or 'tags' not in self.data or 'tags_wd' not in self.data['tags']:
            return 0.0
        tags_dict: dict = self.data['tags']['tags_wd']
        return tags_dict.get(tag, 0.0)

    def calc_score_based_on_tags(self, tags: list[str]) -> None:
        """
        Calcs the score wrt. the given tags and stores the score in the object.
        It also stores the contributing tags in the object.
        """
        current_score = 0.0
        contributing_tags: List[Tuple[str, float]] = []
        if self.data and 'tags' in self.data and 'tags_wd' in self.data['tags']:
            wd_tags = self.data['tags']['tags_wd']
            for o_tag in tags:
                if o_tag in wd_tags:
                    current_score += wd_tags[o_tag]
                    contributing_tags.append((o_tag, wd_tags[o_tag]))
        self.score = current_score
        self.contributing_tags = contributing_tags

    def run_operation(self, value: Any) -> int:
        if self.operation == 'nop':
            return True
        elif self.operation == 'rate':
            return self.update_rating(value)
        elif self.operation == 'scene':
            tags = {'scene': value}
            return self.update_tags(tags)
        else:
            return False

    def export_train(self, to_folder: str, trigger: str = '', export_cap_files=False) -> None:
        """
        Exports all necessary training files to the export folder:
        1. copy the training image from the url to_folder/image_id.png
        2. create a to_folder/image_id.tags file with comma seperated prompt tags as on string
        """
        export_path = Path(to_folder)
        export_path.mkdir(parents=True, exist_ok=True)
        train_path = export_path / 'train'
        train_path.mkdir(parents=True, exist_ok=True)
        images_path = train_path / 'images'
        images_path.mkdir(parents=True, exist_ok=True)
        if export_cap_files:
            text_path = train_path / 'text'
            text_path.mkdir(parents=True, exist_ok=True)

        # 1. Copy the training image by just trying its url. if url doesnt exist, abort.
        train_image_path_str = self.url_train_image
        if not train_image_path_str:
            print(f'No training image URL found for image {self.id}. Aborting export.')
            return

        train_image_source_path = Path(train_image_path_str)
        if not train_image_source_path.exists():
            print(
                f'Training image file not found at {train_image_source_path} for image {
                    self.id
                }. Aborting export.'
            )
            return

        train_image_destination_path = images_path / f'{self.id}.png'
        try:
            import shutil

            shutil.copy(train_image_source_path, train_image_destination_path)
            print(f'Copied training image to {train_image_destination_path}')
        except Exception as e:
            print(f'Error copying training image for {self.id}: {e}')
            return

        # 3. or expand metadata.jsonl
        # line_json = {"file_name": "images/" + train_image_destination_path.name, "text": caption_string, "tags": json.dumps(self.tags)}
        prompt = self._prompt_meta
        caption = self._hfd_caption_search
        capjoy = self._hfd_caption_joy
        line_json = {
            'file_name': 'images/' + train_image_destination_path.name,
            'tags': json.dumps(self.tags),
            'prompt': prompt,
            'caption': caption,
            'caption_joy': capjoy,
        }
        # add line to extisting "metadata.jsonl" or create file if not exist
        metadata_file_path = train_path / 'metadata.jsonl'
        try:
            with open(metadata_file_path, 'a', encoding='utf-8') as f:
                json.dump(line_json, f)
                f.write('\n')
            print(f'Added metadata to {metadata_file_path}')
        except Exception as e:
            print(f'Error writing to metadata.jsonl for {self.id}: {e}')
