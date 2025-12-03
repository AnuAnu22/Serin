import lmstudio as lms
import asyncio

#async def load_one_model():
#	async with lms.AsyncClient() as client:
#    		model = await client.llm.model("llama-3.2-3b-instruct-uncensored")
#async def load_more_model():
#	async with lms.AsyncClient() as client:
#		model = await client.llm.load_new_instance("llama-3.2-3b-instruct-uncensored")
#		another_model = await client.llm.load_new_instance("llama-3.2-1b-instruct")


downloaded = lms.list_downloaded_models()
llm_only = lms.list_downloaded_models("llm")
embedding_only = lms.list_downloaded_models("embedding")

for model in downloaded:
	model[0]
	print(model[0])

#if __name__ == "__main__":
#    asyncio.run(load_more_model())