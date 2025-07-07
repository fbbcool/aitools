from typing import List, Dict, Any, Optional, Tuple
from bson.objectid import ObjectId

# Local imports for DBManager and Image classes
from aidb.dbmanager import DBManager
from aidb.image import Image

class Query:
    """
    A class to perform queries on image metadata stored in MongoDB
    and return results as a list of Image objects.
    """

    def __init__(self, db_manager: DBManager) -> None:
        """
        Initializes the Query object with a reference to the DBManager.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError(f"db_manager must be an instance of DBManager. {db_manager}")
        
        self._db_manager = db_manager
        print("Query object initialized.")

    def query_images(self, query: Optional[Dict[str, Any]] = None) -> List[Image]:
        """
        Queries the 'images' collection in the database and returns a list
        of Image objects matching the given query.

        Args:
            query (Optional[Dict[str, Any]]): A dictionary representing the MongoDB query.
                                               If None, all image documents will be returned.
                                               When querying by '_id' or 'container_db_id',
                                               ensure the values are ObjectId instances.

        Returns:
            List[Image]: A list of Image objects matching the query. Returns an empty list
                         if no images are found or if there's a database error.
        """
        print(f"Executing query for images: {query}")
        
        # Ensure _id, container_db_id and rating in query are ObjectId if they are strings
        processed_query = {}
        if query:
            for key, value in query.items():
                if key == "_id" or key == "container_db_id":
                    try:
                        processed_query[key] = ObjectId(value)
                    except Exception:
                        print(f"Warning: Invalid ObjectId format for '{key}': {value}. Skipping this query parameter.")
                        # If an invalid ObjectId is provided, it's safer to skip it
                        # or raise an error, depending on desired strictness.
                        continue
                else:
                    processed_query[key] = value

        image_docs = self._db_manager.find_documents('images', processed_query)
        
        image_objects: List[Image] = []
        if image_docs:
            for doc in image_docs:
                # MongoDB's _id is an ObjectId, convert to string for Image class constructor
                if '_id' in doc:
                    try:
                        image_objects.append(Image(self._db_manager, str(doc['_id']), doc=doc))
                    except ValueError as e:
                        print(f"Error creating Image object for document {doc.get('_id')}: {e}")
                else:
                    print(f"Warning: Document found without '_id' field: {doc}")
        else:
            print("No image documents found matching the query.")
            
        return image_objects
    
    def query_by_tags(self, tags_mand: List[str], tags_opt: List[str], rating_min: int, rating_max: int, bodypart: str) -> List[Image]:
        """
        Queries images based on mandatory and optional tags, and a rating range.

        Args:
            tags_mand (List[str]): List of tags that must be present in the image's tags_wd.
            tags_opt (List[str]): List of optional tags that contribute to a score.
            rating_min (int): Minimum rating (inclusive).
            rating_max (int): Maximum rating (inclusive).

        Returns:
            List[Image]: A list of Image objects matching the criteria.
        """
        print(f"Querying by tags: Mandatory={tags_mand}, Optional={tags_opt}, Rating={rating_min}-{rating_max}")

        mongo_query: Dict[str, Any] = {}

        # Add mandatory tags criteria
        if tags_mand:
            # For each mandatory tag, ensure it exists in tags.tags_wd
            # MongoDB query for existence of a field: { "field": { "$exists": true } }
            # To check for multiple mandatory tags, use $and
            mongo_query['$and'] = [{f'tags.tags_wd.{tag}': {'$exists': True}} for tag in tags_mand]

        # Add ratings filter criteria
        # The rating field is directly in the image document
        mongo_query['rating'] = {'$gte': rating_min, '$lte': rating_max}
        print(f"Mongo query: {mongo_query}")

        # Execute the query to get image documents
        image_docs = self._db_manager.find_documents('images', mongo_query)

        image_objects: List[Image] = []
        if not image_docs:
            return []

        for doc in image_docs:
            if '_id' in doc:
                try:
                    # Create ONE Image object, passing the pre-fetched doc to avoid re-querying
                    img_obj = Image(self._db_manager, str(doc['_id']), doc=doc)
                    # Use the object's own method to calculate the score
                    img_obj.calc_score_based_on_tags(tags_opt+tags_mand)
                    image_objects.append(img_obj)
                except ValueError as e:
                    print(f"Error creating Image object for document {doc.get('_id')}: {e}")
        
        # ignore bodypart
        if bodypart == "Ignore":
            return self._sort_images_by_score(image_objects)

        # filter bodyparts
        if bodypart and bodypart != "Empty":
            image_objects = [img for img in image_objects if bodypart in img.get_tags_custom("bodypart")]
        elif bodypart == "Empty":
            # only imgs w/ empty bodyparts
            image_objects = [img for img in image_objects if not img.get_tags_custom("bodypart")]
        
        return self._sort_images_by_score(image_objects)
    
    def query_by_rating(self, rating_min: int, rating_max: int) -> List[Image]:
        """
        Queries images based on a rating range.
        """
        print(f"Querying by rating: Minimum={rating_min}, Maximum={rating_max}")

        mongo_query: Dict[str, Any] = {
            'rating': {'$gte': rating_min, '$lte': rating_max}
        }

        image_docs = self._db_manager.find_documents('images', mongo_query)

        image_objects: List[Image] = []
        if not image_docs:
            return []

        for doc in image_docs:
            if '_id' in doc:
                try:
                    img_obj = Image(self._db_manager, str(doc['_id']), doc=doc)
                    image_objects.append(img_obj)
                except ValueError as e:
                    print(f"Error creating Image object for document {doc.get('_id')}: {e}")
        
        return image_objects
    
    def query_by_bodyparts(self, bodyparts: list[str], rating_min: int = 3, rating_max: int = 5) -> List[Image]:
        """
        Queries images based on the bodyparts tags and a rating range.
        """
        print(f"Querying by bodyparts: {bodyparts}, Rating={rating_min}-{rating_max}")

        mongo_query: Dict[str, Any] = {
            'rating': {'$gte': rating_min, '$lte': rating_max}
        }

        # If bodyparts are specified, add them to the query
        if bodyparts:
            # Use $all to ensure all specified bodyparts are present in the 'custom.bodypart' array
            # Or use $in if any of the specified bodyparts is sufficient
            mongo_query['tags.custom.bodypart'] = {'$in': bodyparts}
        
        image_docs = self._db_manager.find_documents('images', mongo_query)

        image_objects: List[Image] = []
        if not image_docs:
            return []

        for doc in image_docs:
            if '_id' in doc:
                try:
                    img_obj = Image(self._db_manager, str(doc['_id']), doc=doc)
                    image_objects.append(img_obj)
                except ValueError as e:
                    print(f"Error creating Image object for document {doc.get('_id')}: {e}")
        
        return image_objects


    @staticmethod
    def _sort_images_by_score(images: List[Image]) -> List[Image]:
        """
        Sorts a list of Image objects by their 'score' attribute in descending order.
        Assumes that the 'score' attribute has been set on the Image objects.
        """
        return sorted(images, key=lambda img: getattr(img, 'score', 0.0), reverse=True)
    