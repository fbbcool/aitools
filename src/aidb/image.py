import pathlib
from typing import List, Dict, Literal, Optional, Union, Any, Tuple
from bson.objectid import ObjectId
from PIL import Image as PILImage
import numpy as np # Import Image from Pillow and alias it to avoid conflict with our class name

from aidb.dbmanager import DBManager # Updated import
from aidb.tagger import tagger_wd as tagger # Updated import

class Image:
    """
    A class to manage and update metadata for a single image document
    in the MongoDB database.
    """

    def __init__(self, db_manager: DBManager, image_id: str, doc: Optional[Dict[str, Any]] = None) -> None:
        """
        Initializes the Image object with a reference to the DBManager
        and the MongoDB _id of the image.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
            image_id (str): The string representation of the MongoDB '_id' for this image.
            doc (Optional[Dict[str, Any]]): An optional pre-fetched document from the database.
                                             If provided, it prevents an extra database call.
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError("db_manager must be an instance of DBManager.")
        
        # Validate if image_id is a valid ObjectId string
        try:
            ObjectId(image_id)
        except Exception:
            raise ValueError(f"Invalid image_id format: '{image_id}'. Must be a valid MongoDB ObjectId string.")

        self._db_manager = db_manager
        self._image_id = image_id
        self._data = doc # Store the pre-fetched document
        self.score = 0.0
        self.contributing_tags = []
        self.operation : Literal['nop','rate','scene'] = 'nop'


    @property
    def image_id(self) -> str:
        """Returns the MongoDB _id of this image."""
        return self._image_id
    
    @property
    def data(self) -> dict:
        """
        Fetches and caches the image's metadata from the database.
        """
        if self._data is not None:
            return self._data

        # Fetch the image document from the database
        image_doc = self._db_manager.find_documents('images', {"_id": ObjectId(self._image_id)})

        if not image_doc:
            print(f"Error: Image with ID '{self._image_id}' not found in the database.")
            return None
        
        # Assuming find_documents returns a list, take the first one
        self._data = image_doc[0]
        return self._data

    
    @property
    def tags(self) -> dict:
        """Returns the tags dictionary from the image data."""
        if self.data is None:
            return {}
        return self.data.get("tags", {}) # Use .get to safely access, return empty dict if 'tags' is missing
    
    @property
    def tags_prompt(self) -> list[str]:
        return tagger.tags_prompt(self.tags)
    
    @property
    def rating(self) -> int | None:
        """Returns the rating of the image."""
        if self.data is None:
            return None
        return self.data.get("rating")
    
    def set_rating(self, rating: int) -> int:
        """Sets the rating of the image."""
        if not isinstance(rating, int):
            raise TypeError("Rating must be an integer.")
        if not (-2 <= rating <= 5):
            raise ValueError("Rating must be between -2 and 5.")
        print(f"Setting rating for image {self._image_id} to {rating}")
        return self._db_manager.update_image(self._image_id, rating=rating)
    
    def get_tags_custom(self, category: str) -> list[str]:
        """Returns tags of a custom category."""
        tags = self.tags
        if "custom" in tags:
            custom_tags = tags["custom"]
        else:
            return []
        if category in custom_tags:
            return custom_tags[category]
        else:
            return []


    def set_tags_custom(self, category: str, tags_category: list[str]) -> int:
        """Sets custom category tags"""
        tags = self.tags
        tags_custom = tags["custom"] if "custom" in tags else {}
        tags_custom[category] = tags_category
        return self.update_tags({"custom": tags_custom})
    
    def generate_tags(self) -> dict:
        """
        Generates tags for the image using the configured tagger.
        Requires the PIL image to be loadable.
        """
        if self.pil:
            return tagger.tags(self.pil)
        else:
            print(f"Warning: Cannot generate tags for image {self._image_id} as PIL image could not be loaded.")
            return {}

    def get_full_path(self) -> Optional[pathlib.Path]:
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

        container_local_path_str = self.data.get("container_local_path")
        relative_url_str = self.data.get("relative_url")

        if container_local_path_str is None or relative_url_str is None:
            print(f"Error: Missing 'container_local_path' or 'relative_url' for image ID '{self._image_id}'.")
            return None

        try:
            base_path = pathlib.Path(container_local_path_str)
            relative_path = pathlib.Path(relative_url_str)
            full_path = base_path / relative_path
            return full_path
        except Exception as e:
            print(f"Error constructing full path for image ID '{self._image_id}': {e}")
            return None

    @property
    def pil(self) -> Optional[PILImage.Image]:
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
            print(f"Error: Image file not found at '{full_path}' for image ID '{self._image_id}'.")
            return None

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
    def thumbnail(self) -> Optional[PILImage.Image]:
        """
        Retrieves the thumbnail image as a PIL (Pillow) Image object.
        If a thumbnail URL exists in the database and the file exists, it loads it.
        Otherwise, it generates a new thumbnail, saves it, updates the database,
        and then loads and returns the newly created thumbnail.
        """
        if self.data is None:
            print(f"Cannot get thumbnail: Image data not available for ID '{self._image_id}'.")
            return None

        thumbnail_url_str = self.data.get("thumbnail_url")
        
        # Get thumbnail settings from DBManager's properties
        output_thumbnail_dir = self._db_manager.default_thumbnail_dir
        output_thumbnail_size = self._db_manager.default_thumbnail_size

        # 1. Check if thumbnail URL exists and file exists on disk
        if thumbnail_url_str:
            thumbnail_path = pathlib.Path(thumbnail_url_str)
            if thumbnail_path.exists():
                try:
                    thumb_pil_image = PILImage.open(thumbnail_path)
                    # print(f"Successfully loaded existing thumbnail for ID '{self._image_id}'.")
                    return thumb_pil_image
                except Exception as e:
                    print(f"Warning: Could not load existing thumbnail '{thumbnail_path}' for ID '{self._image_id}': {e}. Attempting to regenerate.")
        
        # 2. If not found or failed to load, generate and save a new one
        print(f"Generating new thumbnail for image ID '{self._image_id}'.")
        created_thumbnail_path = self.save_thumbnail_and_update_db(
            output_directory=output_thumbnail_dir,
            thumbnail_size=output_thumbnail_size
        )

        if created_thumbnail_path:
            try:
                # Load the newly created thumbnail
                new_thumb_pil_image = PILImage.open(created_thumbnail_path)
                print(f"Successfully loaded newly generated thumbnail for ID '{self._image_id}'.")
                return new_thumb_pil_image
            except Exception as e:
                print(f"Error loading newly created thumbnail '{created_thumbnail_path}' for ID '{self._image_id}': {e}")
                return None
        else:
            print(f"Failed to create or save thumbnail for image ID '{self._image_id}'.")
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

        train_image_url_str = self.data.get("train_image_url")
        
        # Get training image settings from DBManager's properties
        output_train_image_dir = self._db_manager.default_train_image_dir
        output_train_image_size = self._db_manager.default_train_image_size

        # 1. Check if training image URL exists and file exists on disk
        if train_image_url_str:
            train_image_path = pathlib.Path(train_image_url_str)
            if train_image_path.exists():
                try:
                    train_pil_image = PILImage.open(train_image_path)
                    # print(f"Successfully loaded existing training image for ID '{self._image_id}'.")
                    return train_pil_image
                except Exception as e:
                    print(f"Warning: Could not load existing training image '{train_image_path}' for ID '{self._image_id}': {e}. Attempting to regenerate.")
        
        # 2. If not found or failed to load, generate and save a new one
        print(f"Generating new training image for image ID '{self._image_id}'.")
        created_train_image_path = self.save_train_image_and_update_db(
            output_directory=output_train_image_dir,
            train_image_size=output_train_image_size
        )

        if created_train_image_path:
            try:
                # Load the newly created training image
                new_train_pil_image = PILImage.open(created_train_image_path)
                print(f"Successfully loaded newly generated training image for ID '{self._image_id}'.")
                return new_train_pil_image
            except Exception as e:
                print(f"Error loading newly created training image '{created_train_image_path}' for ID '{self._image_id}': {e}")
                return None
        else:
            print(f"Failed to create or save training image for image ID '{self._image_id}'.")
            return None
    
    @property
    def url_train_image(self) -> str | None:
        """
        Returns the URL of the training image.
        """
        if self.data is None:
            return None
        return self.data.get("train_image_url")

    @property
    def statistics(self) -> dict:
        """
        Returns the statistics section of the metadata.
        
        If no statistics are available, it returns an empty dictionary.
        """
        if self.data is None:
            return {}
        return self.data.get("statistics", {})
    
    @property
    def focus_vector(self) -> np.ndarray | None:
        """
        Returns the focus vector  from the statistics of the image as an np.ndarray.

        If no focus vector is available, it returns None.
        """
        if self.statistics is None:
            return None
        
        focus_vector_list = self.statistics.get("focus_vector")
        if focus_vector_list is None:
            return None
        
        return np.array(focus_vector_list)

    @property
    def neighbors(self) -> dict[str,float]:
        """
        Returns the neighbors dictionary from the metadata.

        If no neighbors are available, it returns an empty dictionary.
        """
        if self.statistics is None:
            return {}
        return self.statistics.get("neighbors", {})
    
    @property
    def neighbor0(self) -> tuple[str,float] | None:
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

    def save_png_image(self, 
                       output_path: Union[str, pathlib.Path], 
                       compression: int = 6, 
                       size: Optional[Tuple[int, int]] = None) -> Optional[pathlib.Path]:
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

        output_dir_path = pathlib.Path(output_path)
        output_dir_path.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

        output_filename = f"{self._image_id}.png"
        full_output_path = output_dir_path / output_filename

        try:
            # Handle resizing if size is specified
            if size is not None:
                if not (isinstance(size, tuple) and len(size) == 2 and all(isinstance(dim, int) and dim > 0 for dim in size)):
                    print(f"Error: 'size' must be a tuple of two positive integers (width, height). Got {size}")
                    return None
                
                # Create a copy to resize, keeping original PIL image intact if needed elsewhere
                resized_pil_image = pil_image.copy()
                resized_pil_image.resize((size[0], size[1]), PILImage.Resampling.LANCZOS)
                pil_image_to_save = resized_pil_image
                print(f"Image '{self._image_id}' resized to {size[0]}x{size[1]}.")
            else:
                pil_image_to_save = pil_image

            # Save the image with specified compression
            pil_image_to_save.save(full_output_path, "PNG", optimize=True, compress_level=compression)
            print(f"Image '{self._image_id}' saved successfully to '{full_output_path}' with compression level {compression}.")
            return full_output_path
        except Exception as e:
            print(f"Error saving PNG image '{self._image_id}' to '{full_output_path}': {e}")
            return None

    def save_thumbnail_and_update_db(self, 
                                     output_directory: Union[str, pathlib.Path], 
                                     thumbnail_size: Tuple[int, int] = (128, 128)
                                    ) -> Optional[str]:
        """
        Generates a thumbnail for the image, saves it as a PNG in the specified directory,
        and updates the 'thumbnail_url' field in the database.

        Args:
            output_directory (Union[str, pathlib.Path]): The directory where the thumbnail
                                                          should be saved.
            thumbnail_size (Tuple[int, int]): A tuple (width, height) for the maximum
                                              dimensions of the thumbnail. Aspect ratio is preserved.
                                              Defaults to (128, 128).

        Returns:
            Optional[str]: The full local path string of the saved thumbnail if successful,
                           otherwise None.
        """
        pil_image = self.pil
        if pil_image is None:
            print(f"Failed to get PIL image for thumbnail generation for ID '{self._image_id}'.")
            return None

        output_dir_path = pathlib.Path(output_directory)
        output_dir_path.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

        thumbnail_filename = f"{self._image_id}_thumb.png"
        full_thumbnail_path = output_dir_path / thumbnail_filename

        try:
            # Create a copy to ensure the original PIL image object is not modified
            thumb_pil_image = pil_image.copy()
            thumb_pil_image.thumbnail(thumbnail_size, PILImage.Resampling.LANCZOS) # Preserves aspect ratio
            
            thumb_pil_image.save(full_thumbnail_path, "PNG", optimize=True, compress_level=6)
            print(f"Thumbnail for image '{self._image_id}' saved to '{full_thumbnail_path}'.")

            # Update the database with the new thumbnail URL
            # For simplicity, we'll store the local file path as the URL.
            # In a web application, this might be a URL to a served static file.
            updated_count = self._db_manager.update_image(
                self._image_id, 
                thumbnail_url=str(full_thumbnail_path)
            )

            if updated_count and updated_count > 0:
                print(f"Thumbnail URL updated in DB for image '{self._image_id}'.")
                # Clear cached data so next .data access fetches updated thumbnail_url
                self._data = None 
                return str(full_thumbnail_path)
            else:
                print(f"Failed to update thumbnail URL in DB for image '{self._image_id}'.")
                return None

        except Exception as e:
            print(f"Error generating or saving thumbnail for image '{self._image_id}': {e}")
            return None

    def save_train_image_and_update_db(self, 
                                     output_directory: Union[str, pathlib.Path], 
                                     train_image_size: Tuple[int, int] = (128, 128)
                                    ) -> Optional[str]:
        """
        Generates a training image for the image, saves it as a PNG in the specified directory,
        and updates the 'train_image_url' field in the database.
        """
        pil_image = self.pil
        if pil_image is None:
            print(f"Failed to get PIL image for thumbnail generation for ID '{self._image_id}'.")
            return None

        output_dir_path = pathlib.Path(output_directory)
        output_dir_path.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

        train_img_filename = f"{self._image_id}_1024.png"
        full_train_img_path = output_dir_path / train_img_filename

        try:
            # Create a copy to ensure the original PIL image object is not modified
            train_pil_image = pil_image.copy()
            # Rescale longest edge to size, upscaling if necessary
            width, height = train_pil_image.size
            if width > height:
                # Landscape or square
                new_width = train_image_size[0]
                new_height = int(new_width * height / width) if width > 0 else 0
                train_pil_image = train_pil_image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
            else:
                # Portrait
                new_height = train_image_size[1]
                new_width = int(new_height * width / height) if height > 0 else 0
                train_pil_image = train_pil_image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

            
            train_pil_image.save(full_train_img_path, "PNG", optimize=True, compress_level=6)
            print(f"Train image for image '{self._image_id}' saved to '{full_train_img_path}'.")

            # Update the database with the new thumbnail URL
            # For simplicity, we'll store the local file path as the URL.
            # In a web application, this might be a URL to a served static file.
            updated_count = self._db_manager.update_image(
                self._image_id, 
                train_image_url=str(full_train_img_path)
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
        print(f"Updating description for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, description=description)

    def update_creation_date(self, creation_date: str) -> Optional[int]:
        """Updates the creation_date field of the image."""
        print(f"Updating creation_date for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, creation_date=creation_date)

    def update_last_modified_date(self, last_modified_date: str) -> Optional[int]:
        """Updates the last_modified_date field of the image."""
        print(f"Updating last_modified_date for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, last_modified_date=last_modified_date)

    def update_tags(self, tags: List[Dict[str, Any]]) -> Optional[int]:
        """Updates the tags field of the image."""
        print(f"Updating tags for image {self._image_id}")
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
        print(f"Updating dimensions for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, dimensions=dimensions)

    def update_thumbnail_url(self, thumbnail_url: str) -> Optional[int]:
        """Updates the thumbnail_url field of the image."""
        print(f"Updating thumbnail_url for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, thumbnail_url=thumbnail_url)

    def update_rating(self, rating: int) -> Optional[int]:
        """Updates the rating field of the image."""
        print(f"Updating rating for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, rating=rating)

    def update_category(self, category: str) -> Optional[int]:
        """Updates the category field of the image."""
        print(f"Updating category for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, category=category)

    def update_container_db_id(self, container_db_id: str) -> Optional[int]:
        """Updates the container_db_id field of the image."""
        print(f"Updating container_db_id for image {self._image_id}")
        return self._db_manager.update_image(self._image_id, container_db_id=container_db_id)

    def update_all(self, 
                   description: Optional[List[Dict[str, str]]] = None, 
                   creation_date: Optional[str] = None, 
                   last_modified_date: Optional[str] = None, 
                   tags: Optional[List[Dict[str, Any]]] = None,
                   dimensions: Optional[Dict[str, Union[int, str]]] = None, 
                   thumbnail_url: Optional[str] = None, 
                   rating: Optional[int] = None, 
                   category: Optional[str] = None,
                   container_db_id: Optional[str] = None
                   ) -> Optional[int]:
        """
        Updates multiple fields of the image document.
        Any parameter left as None will not be updated.
        """
        print(f"Updating multiple fields for image {self._image_id}")
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
            container_db_id=container_db_id
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
        if self.data is None or "tags" not in self.data or "tags_wd" not in self.data["tags"]:
            return 0.0
        tags_dict: dict = self.data["tags"]["tags_wd"]
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
            tags = {"scene": value}
            return self.update_tags(tags)
        else:
            return False
    
    def export_train(self, to_folder: str) -> None:
        """
        Exports all necessary training files to the export folder:
        1. copy the training image from the url to_folder/image_id.png
        2. create a to_folder/image_id.tags file with comma seperated prompt tags as on string
        """
        export_path = pathlib.Path(to_folder)
        export_path.mkdir(parents=True, exist_ok=True)

        # 1. Copy the training image by just trying its url. if url doesnt exist, abort.
        train_image_path_str = self.url_train_image
        if not train_image_path_str:
            print(f"No training image URL found for image {self.image_id}. Aborting export.")
            return

        train_image_source_path = pathlib.Path(train_image_path_str)
        if not train_image_source_path.exists():
            print(f"Training image file not found at {train_image_source_path} for image {self.image_id}. Aborting export.")
            return

        train_image_destination_path = export_path / f"{self.image_id}.png"
        try:
            import shutil
            shutil.copy(train_image_source_path, train_image_destination_path)
            print(f"Copied training image to {train_image_destination_path}")
        except Exception as e:
            print(f"Error copying training image for {self.image_id}: {e}")
            return
            

        # 2. Create the tags file
        tags_export_path = export_path / f"{self.image_id}.txt"
        prompt_tags = self.tags_prompt
        if prompt_tags:
            tags_string = ", ".join(prompt_tags)
            try:
                with open(tags_export_path, "w", encoding="utf-8") as f:
                    f.write(tags_string)
                print(f"Exported tags to {tags_export_path}")
            except Exception as e:
                print(f"Error exporting tags for {self.image_id}: {e}")
        else:
            print(f"No prompt tags found for {self.image_id}, skipping tags export.")
            


