"""
MongoDB CDC via Change Streams.

Requires:
  - MongoDB 3.6+ (replica set or sharded cluster)
  - Requires oplog access → replica set deployment
"""
from pymongo import MongoClient
from datetime import datetime

from core.cdc.base_cdc import BaseCDC, CDCEvent


class MongoDBCdc(BaseCDC):

    def __init__(self, client: MongoClient, database_name: str):
        super().__init__(client, database_name)
        self.client = client
        self.db = client[database_name]
        self._resume_token: dict = None
        self._change_stream = None

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def start(self, tables: list[str] | None = None) -> None:
        """
        Open a change stream on the entire database.
        If `tables` (collection names) are specified, only watch those.
        """
        pipeline = []
        if tables:
            pipeline.append({"$match": {"ns.coll": {"$in": tables}}})

        self._change_stream = self.db.watch(pipeline, full_document="updateLookup")

    def capture(self, from_checkpoint: str = ""):
        """
        Consume change stream events and yield CDCEvent.
        `from_checkpoint` is a resume token (JSON-serialized).
        """
        if not self._change_stream:
            return

        if from_checkpoint:
            import json
            try:
                self._change_stream = self.db.watch(
                    resume_after=json.loads(from_checkpoint)
                )
            except Exception:
                pass

        try:
            for change in self._change_stream:
                self._resume_token = change.get("_id")
                op = change.get("operationType", "unknown")
                ns = change.get("ns", {})
                collection = ns.get("coll", "")

                if op == "insert":
                    data = change.get("fullDocument", {})
                    data.pop("_id", None)

                    yield CDCEvent(
                        operation="INSERT",
                        schema_name=self.database_name,
                        table_name=collection,
                        data=data,
                        checkpoint=self.get_checkpoint(),
                        event_time=datetime.utcnow(),
                    )

                elif op == "update":
                    data = change.get("fullDocument", {})
                    data.pop("_id", None)

                    yield CDCEvent(
                        operation="UPDATE",
                        schema_name=self.database_name,
                        table_name=collection,
                        data=data,
                        checkpoint=self.get_checkpoint(),
                        event_time=datetime.utcnow(),
                    )

                elif op == "delete":
                    doc_id = change.get("documentKey", {}).get("_id")
                    data = {"_id": str(doc_id)} if doc_id else {}

                    yield CDCEvent(
                        operation="DELETE",
                        schema_name=self.database_name,
                        table_name=collection,
                        data=data,
                        checkpoint=self.get_checkpoint(),
                        event_time=datetime.utcnow(),
                    )

                elif op == "drop":
                    yield CDCEvent(
                        operation="DROP_TABLE",
                        schema_name=self.database_name,
                        table_name=collection,
                        data={},
                        checkpoint=self.get_checkpoint(),
                        event_time=datetime.utcnow(),
                    )

                elif op == "create":
                    yield CDCEvent(
                        operation="CREATE_TABLE",
                        schema_name=self.database_name,
                        table_name=collection,
                        data={},
                        checkpoint=self.get_checkpoint(),
                        event_time=datetime.utcnow(),
                    )

        except Exception as error:
            print(f"MongoDB CDC error: {error}")

    def stop(self) -> None:
        if self._change_stream:
            self._change_stream.close()
            self._change_stream = None

    def get_checkpoint(self) -> str:
        """Return resume token as JSON string."""
        if self._resume_token:
            import json
            return json.dumps(self._resume_token, default=str)
        return ""
