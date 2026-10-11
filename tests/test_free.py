import unittest,sys
from pathlib import Path
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bot import Bot
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_free(self):
  b=Bot('test');b.api=AsyncMock();await b.handle({'message':{'chat':{'id':1,'type':'private'},'text':'/buy'}});self.assertIn('مجانية',b.api.call_args.kwargs['text'])
 async def test_file(self):
  b=Bot('test');b.api=AsyncMock();await b.handle({'message':{'chat':{'id':1,'type':'private'},'document':{'file_id':'x'}}});self.assertEqual(b.api.call_count,1);self.assertIn('لا يعالج',b.api.call_args.kwargs['text'])
 async def test_group(self):
  b=Bot('test');b.api=AsyncMock();await b.handle({'message':{'chat':{'id':1,'type':'group'},'text':'/start'}});b.api.assert_not_called()
 async def test_navigation_edits_existing_message(self):
  b=Bot('test');b.api=AsyncMock()
  await b.handle({'callback_query':{'id':'cb','data':'review','message':{'message_id':4,'text':'old','chat':{'id':1,'type':'private'}}}})
  self.assertEqual([c.args[0] for c in b.api.call_args_list],['answerCallbackQuery','editMessageText'])
  self.assertIn('الجرعات',b.api.call_args.kwargs['text'])
 async def test_file_metadata_without_download(self):
  b=Bot('test');b.api=AsyncMock()
  await b.handle({'message':{'chat':{'id':1,'type':'private'},'document':{'file_id':'x','file_name':'Study.pdf','file_size':1048576}}})
  self.assertEqual([c.args[0] for c in b.api.call_args_list],['sendMessage'])
  self.assertIn('Study.pdf',b.api.call_args.kwargs['text']);self.assertIn('1.00 MB',b.api.call_args.kwargs['text'])
 async def test_repeated_callback_only_acknowledges(self):
  from bot import REVIEW,menu
  b=Bot('test');b.api=AsyncMock()
  await b.handle({'callback_query':{'id':'cb','data':'review','message':{'message_id':4,'text':REVIEW,'reply_markup':menu('review'),'chat':{'id':1,'type':'private'}}}})
  self.assertEqual([c.args[0] for c in b.api.call_args_list],['answerCallbackQuery'])
