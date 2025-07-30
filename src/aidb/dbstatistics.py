import json

from bson import ObjectId
from aidb.dbmanager import DBManager
from aidb.image import Image # Import the Image class
from aidb.tagger import TAGS_FOCUS
from typing import Dict, Any, List, Optional
from collections import defaultdict
import numpy as np


class Statistics:
    """
    A class to generate various statistics from the image and container metadata
    stored in the MongoDB database.
    """

    def __init__(self, db_manager: DBManager) -> None:
        """
        Initializes the Statistics object with a reference to the DBManager.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError("db_manager must be an instance of DBManager.")
        
        self._db_manager = db_manager
        print("Statistics object initialized.")

    def get_average_tag_occurrence(self, images: Optional[List[Image]] = None) -> Dict[str, float]:
        """
        Calculates the average occurrence (probability) of each unique tag
        found in the 'tags_wd' field.

        Args:
            images (Optional[List[Image]]): A list of Image objects to process.
                                            If None or empty, all images from the
                                            database will be used.

        Returns:
            Dict[str, float]: A dictionary where keys are tag names and values
                              are their average occurrence probabilities.
                              Returns an empty dictionary if no images are found
                              or no tags are present.
        """
        print("Calculating average tag occurrence...")
        
        tag_probabilities_sum: Dict[str, float] = defaultdict(float)
        tag_occurrence_count: Dict[str, int] = defaultdict(int)

        # Determine which images to process
        if images:
            images_to_process = images
            print(f"Processing {len(images_to_process)} provided images for average tag occurrence.")
        else:
            # Retrieve all image documents if no specific list is provided
            print("No specific images provided, fetching all images from database.")
            image_docs = self._db_manager.find_documents(self._db_manager._collection)
            if not image_docs:
                print("No image documents found in the database.")
                return {}
            # Convert documents to Image objects for consistent processing
            images_to_process = [Image(self._db_manager, str(doc['_id']), doc=doc) for doc in image_docs if '_id' in doc]
            print(f"Found {len(images_to_process)} images in the database.")


        if not images_to_process:
            print("No images to process for average tag occurrence.")
            return {}

        for img_obj in images_to_process:
            # Access tags through the Image object's data property
            image_data = img_obj.data
            if image_data and 'tags' in image_data and 'tags_wd' in image_data['tags']:
                wd_tags = image_data['tags']['tags_wd']
                for tag, probability in wd_tags.items():
                    tag_probabilities_sum[tag] += probability
                    tag_occurrence_count[tag] += 1
            else:
                # print(f"Image {img_obj.image_id} has no 'tags' or 'tags_wd' field.")
                pass # Silently skip images without tag data

        average_tag_occurrence: Dict[str, float] = {}
        for tag, total_probability in tag_probabilities_sum.items():
            count = tag_occurrence_count[tag]
            if count > 0:
                average_tag_occurrence[tag] = total_probability / count
            else:
                average_tag_occurrence[tag] = 0.0 
        
        print(f"Finished calculating average tag occurrence for {len(average_tag_occurrence)} unique tags.")
        return average_tag_occurrence

    def get_absolute_tag_occurrence(self, images: Optional[List[Image]] = None) -> Dict[str, int]:
        """
        Calculates the absolute occurrence (frequency) of each unique tag
        found in the 'tags_wd' field.

        Args:
            images (Optional[List[Image]]): A list of Image objects to process.
                                            If None or empty, all images from the
                                            database will be used.

        Returns:
            Dict[str, int]: A dictionary where keys are tag names and values
                            are their absolute occurrence counts.
                            Returns an empty dictionary if no images are found
                            or no tags are present.
        """
        print("Calculating absolute tag occurrence...")
        
        tag_counts: Dict[str, int] = defaultdict(int)

        # Determine which images to process
        if images:
            images_to_process = images
            print(f"Processing {len(images_to_process)} provided images for absolute tag occurrence.")
        else:
            # Retrieve all image documents if no specific list is provided
            print("No specific images provided, fetching all images from database.")
            image_docs = self._db_manager.find_documents('images')
            if not image_docs:
                print("No image documents found in the database.")
                return {}
            # Convert documents to Image objects for consistent processing
            images_to_process = [Image(self._db_manager, str(doc['_id']), doc=doc) for doc in image_docs if '_id' in doc]
            print(f"Found {len(images_to_process)} images in the database.")

        if not images_to_process:
            print("No images to process for absolute tag occurrence.")
            return {}

        for img_obj in images_to_process:
            # Access tags through the Image object's data property
            image_data = img_obj.data
            if image_data and 'tags' in image_data and 'tags_wd' in image_data['tags']:
                wd_tags = image_data['tags']['tags_wd']
                for tag in wd_tags.keys(): # Just count the presence of the tag
                    tag_counts[tag] += 1
            else:
                pass # Silently skip images without tag data

        print(f"Finished calculating absolute tag occurrence for {len(tag_counts)} unique tags.")
        return dict(tag_counts) # Convert defaultdict to a regular dict for return
    
    @property
    def img_rand(self) -> Image:
        """picks a random existing image from the db."""
        image_docs = self._db_manager.find_documents(self._db_manager._collection)
        if not image_docs:
            raise ValueError("No images found in the database.")
        
        # Pick a random document
        random_doc = image_docs[np.random.randint(len(image_docs))]
        
        # Create and return an Image object
        return Image(self._db_manager, str(random_doc['_id']), doc=random_doc)
        

    def img_calc_focus_vector(self, img: Image | str) -> np.ndarray:
        """takes an image or image id and builds a numpy vector of its tag probabilities wrt. TAGS_FOCUS"""
        if isinstance(img, str):
            # Assuming img is an image_id string, create an Image object
            img_obj = Image(self._db_manager, img)
        elif isinstance(img, Image):
            img_obj = img
        else:
            raise TypeError("Input must be an Image object or an image_id string.")

        focus_vector = np.zeros(len(TAGS_FOCUS))
        for i, tag in enumerate(TAGS_FOCUS.keys()):
            focus_vector[i] = img_obj.get_tag_probability(tag)
        return focus_vector
    
    def dist_img(self, img0: Image | str, img1: Image | str) -> float:
        """calcs a distance of 2 imgs based on the focus vector"""
        vec0 = self.img_calc_focus_vector(img0)
        vec1 = self.img_calc_focus_vector(img1)
        return self.dist_focus_vector(vec0, vec1)
    
    def dist_img_list(self, img0: Image | str, imgl: list[Image] | list[str] = [], self_compare: bool = False) -> dict[str,float]:
        """calcs a dictionary of image ids as keys and its distance to img0 as values. if the image list is empty, all images in the db will be used"""
        distances: dict[str,float] = {}
        if not imgl:
            # If imgl is empty, use all images from the database
            image_docs = self._db_manager.find_documents(self._db_manager._collection)
            if not image_docs:
                return distances # No images in DB
            
            # Convert documents to Image objects for consistent processing
            images_to_compare = [Image(self._db_manager, str(doc['_id']), doc=doc) for doc in image_docs if '_id' in doc]
        else:
            images_to_compare = []
            for item in imgl:
                if isinstance(item, str):
                    images_to_compare.append(Image(self._db_manager, item))
                elif isinstance(item, Image):
                    images_to_compare.append(item)
                else:
                    print(f"Warning: Skipping invalid item in imgl: {item}")
                    continue

        if not images_to_compare:
            return distances

        # Calculate the focus vector for the reference image once
        vec0 = self.img_calc_focus_vector(img0)

        for img_to_compare in images_to_compare:
            # Ensure we don't compare an image to itself if it's in the list
            if not self_compare:
                if img_to_compare.id == (img0.id if isinstance(img0, Image) else img0):
                    continue
            
            vec_compare = self.img_calc_focus_vector(img_to_compare)
            distance = self.dist_focus_vector(vec0, vec_compare)
            distances[img_to_compare.id] = distance
        
        return Statistics.sort_tags(distances, highest2lowest=False)


    def img_statistics_init(self, img: Image | str, force: bool = False) -> None:
        """
        Creates and writes a Statistics section in the image metadata if not already present.
        If already present, does nothing.
        """
        if isinstance(img, str):
            img_obj = Image(self._db_manager, img)
        elif isinstance(img, Image):
            img_obj = img
        else:
            raise TypeError("Input must be an Image object or an image_id string.")

        # Check if 'statistics' field already exists
        if img_obj.data and 'statistics' in img_obj.data:
            print(f"Statistics already initialized for image {img_obj.id}.")
            if not force:
                print(f"\tNo force option: Skipping!")
                return
        
        # create an empty statistics section in the db and store it
        self._db_manager.img_add_field(img.id, 'statistics', {}, force=True)

        # Initialize an empty statistics dictionary
        initial_statistics = {
            "focus_vector": self.img_calc_focus_vector(img_obj).tolist(), # Store as list for JSON/BSON compatibility
            "neighbors": {}, # dict of the closest 10 image ids with distance value 
        }

        # Update the image document in the database
        update_result = self.img_statistics_save(
            img_obj.id,
            initial_statistics,
            force = True
        )
        if update_result is not None and update_result > 0:
            print(f"Statistics initialized for image {img_obj.id}.")
            # Invalidate cached data to ensure next access includes new 'statistics' field
            img_obj._data = None 
        else:
            print(f"Failed to initialize statistics for image {img_obj.id}.")
                
    def img_statistics_save(self, img: Image | str, statistics: dict, force: bool = False) -> int:
        """
        Writes a statistics dict to the image metadata.

        If the statistics section isn't present, it creates one.
        If the statistics section is already present, it takes the force option into account.
        """
        if isinstance(img, str):
            img_obj = Image(self._db_manager, img)
        elif isinstance(img, Image):
            img_obj = img
        else:
            raise TypeError("Input must be an Image object or an image_id string.")

        # Check if 'statistics' field exists and handle force option
        if img_obj.data and 'statistics' in img_obj.data:
            if not force:
                print(f"Statistics already exist for image {img_obj.id}. Use force=True to overwrite.")
                return 0
            else:
                print(f"Overwriting existing statistics for image {img_obj.id} as force=True.")
        
        # Update the image document in the database
        update_result = self._db_manager.update_document(
            self._db_manager._collection,
            {"_id": ObjectId(img_obj.id)},
            {"$set": {"statistics": statistics}}
        )
        
        if update_result is not None and update_result > 0:
            print(f"Statistics saved for image {img_obj.id}.")
            # Invalidate cached data to ensure next access includes new 'statistics' field
            img_obj._data = None 
            return update_result
        else:
            print(f"Failed to save statistics for image {img_obj.id}.")
            return 0
    
    def imgs_calc_neighborhood(self, imgs: list[Image], size: int = 10) -> dict[str, dict[str, float]]:
        """
        Returns the neighborhood of every image in the list wrt. the other images in the list.

        The neighhood size is given by the size parameter.
        The returned dict has the image id as key and as value a dictionary of neighboring image id's and their distances.
        The individual focus vectors are not calculated rather than read from the image metadata.
        """
        neighborhoods: dict[str, dict[str, float]] = {}
        
        # Pre-calculate all focus vectors to avoid redundant calculations
        focus_vectors: dict[str, np.ndarray] = {}
        for img in imgs:
            focus_vectors[img.id] = img.focus_vector

        for i, img_i in enumerate(imgs):
            current_image_id = img_i.id
            distances_to_others: dict[str, float] = {}
            
            # Retrieve focus vector for the current image
            vec_i = focus_vectors.get(current_image_id)
            if vec_i is None:
                print(f"Warning: Focus vector not found for image {current_image_id}. Skipping.")
                continue

            for j, img_j in enumerate(imgs):
                if i == j: # Don't compare an image to itself
                    continue
                
                other_image_id = img_j.id
                vec_j = focus_vectors.get(other_image_id)
                if vec_j is None:
                    print(f"Warning: Focus vector not found for image {other_image_id}. Skipping comparison with {current_image_id}.")
                    continue

                distance = self.dist_focus_vector(vec_i, vec_j)
                distances_to_others[other_image_id] = distance
            
            # Sort distances and take the top 'size' neighbors
            sorted_distances = sorted(distances_to_others.items(), key=lambda item: item[1])
            
            # Store only the top 'size' neighbors
            neighborhoods[current_image_id] = dict(sorted_distances[:size])
            
        return neighborhoods
    
    def imgs_set_neighborhood(self, neighborhood: dict[str, dict[str, float]], force: bool = False) -> None:
        """
        Writes the neighborhood dict to the image metadata wrt. the force option.
        """
        for image_id, neighbors_data in neighborhood.items():
            img_obj = Image(self._db_manager, image_id)
            
            # Get current statistics, or initialize if not present
            current_statistics = img_obj.statistics
            if not current_statistics:
                print(f"Warning: Statistics not initialized for image {image_id}. Initializing with empty data.")
                current_statistics = {
                    "focus_vector": self.img_calc_focus_vector(img_obj).tolist(),
                    "neighbors": {}
                }
            
            # Update the neighbors section
            if "neighbors" not in current_statistics or force:
                current_statistics["neighbors"] = neighbors_data
            else:
                print(f"Warning: Neighborhood not overwritten for image {image_id}, no force option.")
                return
            
            # Save the updated statistics back to the database
            self.img_statistics_save(image_id, current_statistics, force=force)



    @staticmethod
    def dist_focus_vector(vec0: np.ndarray, vec1: np.ndarray) -> float:
        return np.linalg.norm(vec0 - vec1)

    @staticmethod
    def sort_tags(tags: Dict[str, float], highest2lowest=True) -> Dict[str, float]:
        """
        Sorts a dictionary of tags (tag name to score/occurrence) by their values in descending order.

        Args:
            tags (Dict[str, float]): A dictionary of tags and their associated float values.

        Returns:
            Dict[str, float]: A new dictionary with tags sorted by value in descending order.
        """
        return dict(sorted(tags.items(), key=lambda item: item[1], reverse=highest2lowest))
    
    @staticmethod
    def save_json(data: Any, filename: str) -> None:
        """
        Saves data to a JSON file.

        Args:
            data (Any): The data to save.
            filename (str): The name of the file to save to.
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Data successfully saved to {filename}")
        except IOError as e:
            print(f"Error saving data to {filename}: {e}")
            
    # Placeholder for future methods
    # def get_tag_frequency(self) -> Dict[str, int]:
    #     """
    #     Calculates the frequency of each tag across all images.
    #     """
    #     pass

    # def get_images_by_rating(self) -> Dict[str, int]:
    #     """
    #     Counts images by their rating.
    #     """
    #     pass

    # def get_container_statistics(self) -> List[Dict[str, Any]]:
    #     """
    #     Provides statistics per container, e.g., number of images, average rating.
    #     """
    #     pass
