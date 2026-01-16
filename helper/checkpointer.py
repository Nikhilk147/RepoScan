from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver,CheckpointTuple,Checkpoint,CheckpointMetadata
from langgraph.checkpoint.serde.base import SerializerProtocol
from supabase import create_client
import os
from typing import Optional,Any,Iterator,Sequence,AsyncIterator
import base64
import asyncio

class SupabaseSaver(BaseCheckpointSaver):

    def __init__(self,serde : Optional[SerializerProtocol] = None):
        super().__init__(serde=serde)
        self.client= create_client(supabase_url=os.getenv("SUPABASE_URL"),
                                   supabase_key = os.getenv("SUPABASE_KEY"))

    def get_tuple(self,config:RunnableConfig) -> Optional[CheckpointTuple]:
        section_id = config["configurable"].get("thread_id")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        res = self.client.table("chat_messages").select("*").eq("session_id",section_id).eq("checkpoint_ns",checkpoint_ns)
        if checkpoint_id:
            res = res.eq("checkpoint_id",checkpoint_id)
        else:
            res = res.order("checkpoint_id",desc=True).limit(1)
        res = res.execute()
        if res.data:
            data = res.data[0]
            state_bytes = base64.b64decode(data["state"])
            checkpoint = self.serde.loads_typed((data["checkpoint_type"],state_bytes))
            metadata = data.get("metadata",{})
            return CheckpointTuple(
                config = config,
                checkpoint = checkpoint,
                metadata = metadata,
                parent_config=None
            )
        return None


    def put(self,config:RunnableConfig,checkpoint:Checkpoint,metadata : CheckpointMetadata,new_versions=Any) -> RunnableConfig:

        session_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")
        type_str,blob = self.serde.dumps_typed(checkpoint)
        print(type_str, blob)
        state_text = base64.b64encode(blob).decode("utf-8")
        self.client.table("chat_messages").upsert({
            "session_id":session_id,
            "state": state_text,
            "checkpoint_ns":checkpoint_ns,
            "checkpoint_type": type_str,
            "checkpoint_id":checkpoint_id,
            "metadata":metadata
        }).execute()
        return {
            "configurable":{
                "thread_id": session_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id":checkpoint_id
            }
        }

    def list(self, config: Optional[RunnableConfig], *, filter: Optional[dict] = None,
             before: Optional[RunnableConfig] = None, limit: Optional[int] = None) -> Iterator[CheckpointTuple]:
        pass

    def put_writes(
            self,
            config: RunnableConfig,
            writes: Sequence[tuple[str, Any]],
            task_id: str,
            task_path: str = "",
    ) -> None:
        pass

    # --- Asynchronous Implementations (Required for astream/ainvoke) ---

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Async version of get_tuple."""
        # Using to_thread to prevent blocking the async loop with synchronous DB calls
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata,
                   new_versions: Any) -> RunnableConfig:
        """Async version of put."""
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def alist(self, config: Optional[RunnableConfig], *, filter: Optional[dict] = None,
                    before: Optional[RunnableConfig] = None, limit: Optional[int] = None) -> AsyncIterator[
        CheckpointTuple]:
        """Optional async list implementation."""
        # This can be left as an empty generator if not needed
        if False: yield

    def _parse_checkpoint_data(self, config: RunnableConfig, data: dict) -> CheckpointTuple:
        state_bytes = base64.b64decode(data["state"])
        checkpoint = self.serde.loads_typed((data["checkpoint_type"], state_bytes))
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=data.get("metadata", {}),
            parent_config=None
        )

    async def aput_writes(self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str,
                          task_path: str = "") -> None:
        pass


