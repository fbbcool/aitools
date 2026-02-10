from typing import Literal, Optional, Any
import json
from bson import ObjectId
from bson.errors import InvalidId
import pymongo
import pymongo.collection
import pymongo.database
from pymongo.errors import OperationFailure
import datetime

from .config_reader import ConfigReader


# Define the DBManager class for handling metadata operations
class DBConnection:
    """
    A class to manage connections and operations for MongoDB.
    This version reads its configuration (MongoDB connection, thumbnail settings)
    from a YAML file if specified.
    """

    def __init__(
        self,
        config: Literal['test', 'prod', 'default'] = 'default',
        verbose=1,
    ) -> None:
        """
        Initializes the MongoDB connection. Configuration can be loaded from a YAML file.
        """
        self.config = ConfigReader(config, verbose=verbose)
        self.client: Optional[pymongo.MongoClient] = None
        self.db: Optional[pymongo.database.Database] = None
        self._verbose = verbose

        # Attempt to connect to MongoDB using the (potentially overridden by YAML) settings
        self.client = pymongo.MongoClient(
            self.config.host, self.config.port, serverSelectionTimeoutMS=5000
        )
        # The ismaster command is cheap and does not require auth.
        self.client.admin.command('ismaster')
        self.db = self.client[self.config.db_name]
        self._log(
            f'Successfully connected to MongoDB at {self.config.host}:{self.config.port}, database: {self.config.db_name}'
        )

    def _get_collection(self, collection_name: str) -> Optional[pymongo.collection.Collection]:
        """
        Helper method to get a specific collection from the database.

        Args:
            collection_name (str): The name of the collection to retrieve.

        Returns:
            pymongo.collection.Collection or None: The MongoDB collection object, or None if DB is not connected.
        """
        if self.db is not None:
            return self.db[collection_name]
        else:
            self._log('Database not connected. Cannot access collection.')
            return None

    def insert_document(self, collection_name: str, document: dict[str, Any]) -> Optional[str]:
        """
        Inserts a single document into the specified collection.

        Args:
            collection_name (str): The name of the collection.
            document (dict): The document to insert.

        Returns:
            str or None: The string representation of the MongoDB '_id' of the inserted document, or None on failure.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                result = collection.insert_one(document)
                # MongoDB automatically generates '_id'
                self._log(
                    f"Document inserted into '{collection_name}' with MongoDB _id: {result.inserted_id}"
                )
                return str(result.inserted_id)
            except OperationFailure as e:
                self._log(f"Failed to insert document into '{collection_name}': {e}")
            except Exception as e:
                self._log(
                    f"An unexpected error occurred during insertion into '{collection_name}': {e}"
                )
        return None

    def to_oid(self, id: Any) -> ObjectId | None:
        if isinstance(id, ObjectId):
            return id
        if not isinstance(id, str):
            return None
        try:
            oid = ObjectId(id)
        except InvalidId:
            return None
        return oid

    def datetime_from_oid(self, id: Any) -> datetime.datetime | None:
        oid: ObjectId
        if isinstance(id, ObjectId):
            return id.generation_time
        if not isinstance(id, str):
            return None
        try:
            oid = ObjectId(id)
        except InvalidId:
            return None
        return oid.generation_time

    def find_documents(
        self, collection_name: str, query: Optional[dict[str, Any]] = None
    ) -> list[dict[str, Any]]:
        """
        Finds documents in the specified collection based on a query.
        Note: If querying by '_id', ensure the value is an ObjectId.

        Args:
            collection_name (str): The name of the collection.
            query (dict, optional): The query to filter documents. If None, all documents are returned.

        Returns:
            list: A list of found documents.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                if query is None:
                    query = {}
                return list(collection.find(query))
            except OperationFailure as e:
                self._log(f"Failed to find documents in '{collection_name}': {e}")
            except Exception as e:
                self._log(
                    f"An unexpected error occurred during finding documents in '{collection_name}': {e}"
                )
        return []

    def documents_from_oid(self, collection_name: str, oid: ObjectId) -> list[dict[str, Any]]:
        return self.find_documents(collection_name, query={'_id': oid})

    def update_document(
        self, collection_name: str, query: dict[str, Any], new_values: dict[str, Any]
    ) -> Optional[int]:
        """
        Updates documents in the specified collection.
        Note: If querying by '_id', ensure the value in the query is an ObjectId.

        Args:
            collection_name (str): The name of the collection.
            query (dict): The query to select documents to update.
            new_values (dict): The new values to set. Use MongoDB update operators (e.g., {"$set": {...}}).

        Returns:
            int or None: The number of modified documents, or None on failure.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                result = collection.update_many(query, new_values)
                self._log(f"Modified {result.modified_count} document(s) in '{collection_name}'.")
                return result.modified_count
            except OperationFailure as e:
                self._log(f"Failed to update documents in '{collection_name}': {e}")
            except Exception as e:
                self._log(
                    f"An unexpected error occurred during updating documents in '{collection_name}': {e}"
                )
        return None

    def delete_document(self, collection_name: str, query: dict[str, Any]) -> Optional[int]:
        """
        Deletes documents from the specified collection.
        Note: If querying by '_id', ensure the value in the query is an ObjectId.

        Args:
            collection_name (str): The name of the collection.
            query (dict): The query to select documents to delete.

        Returns:
            int or None: The number of deleted documents, or None on failure.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                result = collection.delete_many(query)
                self._log(f"Deleted {result.deleted_count} document(s) from '{collection_name}'.")
                return result.deleted_count
            except OperationFailure as e:
                self._log(f"Failed to delete documents from '{collection_name}': {e}")
            except Exception as e:
                self._log(
                    f"An unexpected error occurred during deleting documents from '{collection_name}': {e}"
                )
        return None

    def close_connection(self) -> None:
        """
        Closes the MongoDB connection.
        """
        if self.client is not None:
            self.client.close()
            self._log('MongoDB connection closed.')
        else:
            self._log('No active MongoDB connection to close.')

    def export_db(self):
        """exports the current db to a file named like the current db name. if the file already exists, it will be overwritten."""
        if self.db is None:
            self._log('Database not connected. Cannot export.')
            return

        db_name = self.db.name
        export_file_name = f'{db_name}_export.json'

        export_data = {}
        for collection_name in self.db.list_collection_names():
            collection = self.db[collection_name]
            export_data[collection_name] = []
            for document in collection.find({}):
                # Convert ObjectId to string for JSON serialization
                document['_id'] = str(document['_id'])
                # Convert any other ObjectIds in the document to string
                for key, value in document.items():
                    if isinstance(value, ObjectId):
                        document[key] = str(value)
                    elif isinstance(value, list):
                        document[key] = [
                            str(item) if isinstance(item, ObjectId) else item for item in value
                        ]
                export_data[collection_name].append(document)

        try:
            with open(export_file_name, 'w') as f:
                json.dump(export_data, f, indent=4)
            self._log(f"Database '{db_name}' exported successfully to '{export_file_name}'.")
        except IOError as e:
            self._log(f"Error writing export file '{export_file_name}': {e}")
        except Exception as e:
            self._log(f'An unexpected error occurred during database export: {e}')

    def import_db(self, import_file_name: str, db_name: str) -> None:
        """imports a database from a file to a new database. if the database already exists, the export is canceled."""
        if self.client is None:
            self._log('MongoDB client not initialized. Cannot import.')
            return

        # Check if the target database already exists
        if db_name in self.client.list_database_names():
            self._log(
                f"Error: Database '{db_name}' already exists. Import canceled to prevent accidental overwrite."
            )
            self._log('Please drop the existing database or choose a different name for import.')
            return

        try:
            with open(import_file_name, 'r') as f:
                import_data = json.load(f)
        except FileNotFoundError:
            self._log(f"Error: Import file '{import_file_name}' not found.")
            return
        except json.JSONDecodeError as e:
            self._log(f"Error decoding JSON from '{import_file_name}': {e}")
            return
        except Exception as e:
            self._log(
                f"An unexpected error occurred while reading import file '{import_file_name}': {e}"
            )
            return

        # Connect to the new database
        new_db = self.client[db_name]
        self._log(f"Attempting to import data into new database '{db_name}'...")

        for collection_name, documents in import_data.items():
            collection = new_db[collection_name]
            docs_to_insert = []
            for doc in documents:
                # Convert string _id back to ObjectId
                if '_id' in doc:
                    doc['_id'] = ObjectId(doc['_id'])
                # Convert any other ObjectIds back
                for key, value in doc.items():
                    if isinstance(value, str):
                        try:
                            # Check if it's a valid ObjectId string
                            if len(value) == 24 and all(
                                c in '0123456789abcdefABCDEF' for c in value
                            ):
                                doc[key] = ObjectId(value)
                        except Exception:
                            pass  # Not an ObjectId string
                    elif isinstance(value, list):
                        new_list = []
                        for item in value:
                            if isinstance(item, str):
                                try:
                                    if len(item) == 24 and all(
                                        c in '0123456789abcdefABCDEF' for c in item
                                    ):
                                        new_list.append(ObjectId(item))
                                    else:
                                        new_list.append(item)
                                except Exception:
                                    new_list.append(item)
                            else:
                                new_list.append(item)
                        doc[key] = new_list
                docs_to_insert.append(doc)

            if docs_to_insert:
                try:
                    collection.insert_many(docs_to_insert)
                    self._log(
                        f"Imported {len(docs_to_insert)} documents into collection '{collection_name}'."
                    )
                except OperationFailure as e:
                    self._log(f"Error inserting documents into '{collection_name}': {e}")
            else:
                self._log(f"No documents to insert into collection '{collection_name}'.")

        self._log(f"Database '{db_name}' imported successfully from '{import_file_name}'.")
        # Update the current DBManager's connection to the newly imported database
        self.db = new_db
        self._db_name = db_name

    def _log(self, msg: str, level: str = 'message') -> None:
        if self._verbose > 0:
            print(f'[dbc:{level}] {msg}')
