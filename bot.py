import asyncio, os, logging, hmac, time, secrets
from collections import OrderedDict
import aiohttp
from aiohttp import web
from translation import process, TranslationError, MAX_BYTES

LABELS={'line':'📘 ترجمة سطرية','arabic':'📗 عربية كاملة'}
WELCOME='QMR Translate 🩺\nاختر طريقة الترجمة، ثم أرسل ملف PDF نصيًا باللغة الإنجليزية.\n\n📘 سطرية: كل سطر إنجليزي وتحته العربية.\n📗 عربية كاملة: استبدال النص الإنجليزي بالعربية داخل الصفحات إن اتسعت.\n\nالنتيجة تصل هنا كملف PDF. الخدمة مجانية ضمن حدود Gemini والاستضافة؛ لا مدفوعات. لا ترسل بيانات مرضى تعريفية.\n\nيمكنك أيضًا اختيار زر الموقع للترجمة يدويًا عبر Online Doc Translator.'
HELP='أرسل PDF نصيًا، ثم اختر أحد الخيارين أسفل رسالة الملف. يمكنك أيضًا اختيار الوضع قبل الإرسال.\n\nالحد الحالي: 20 MB، و120 صفحة، و150 ألف حرف. الملفات المصوّرة أو المحتوية على صور غير مدعومة حاليًا.\n\nالسطرية تزيد عدد الصفحات. العربية الكاملة تحافظ على ترتيب الصفحات، وقد تختلف فواصل الأسطر؛ إذا لم يتسع النص يُعاد تنسيقه تلقائيًا دون قص.\n\n/status لحالة المعالجة، و/cancel لإلغائها.'
PRIVACY='الملف يُنزّل مؤقتًا للمعالجة، ويُرسل النص إلى Gemini. قد تستخدم Google محتوى المستوى المجاني لتحسين منتجاتها.\n\nاستخدم ملفات تعليمية خالية من بيانات المرضى التعريفية. اختيار وضع الترجمة يؤكد موافقتك على هذه المعالجة.\n\nلا نحفظ الملفات في قاعدة بيانات ولا نسجل محتواها. تُحذف المراجع المؤقتة بعد المعالجة؛ Telegram يحتفظ بالرسائل وفق سياسته.'
REVIEW='راجع الجرعات والأرقام والوحدات والنفي والمصطلحات مقابل الأصل. يفحص البوت اكتمال المقاطع وترتيبها وبعض الأرقام والرموز؛ هذه الفحوص لا تضمن صحة المعنى الطبي.\n\nالترجمة تنقل محتوى المصدر ولا تصحح أخطاءه العلمية. لا تعتمد عليها لاتخاذ قرار علاجي دون مراجعة مختص.'
def button(text,data):return {'text':text,'callback_data':data}
def menu():return {'inline_keyboard':[[button(LABELS['line'],'mode:line'),button(LABELS['arabic'],'mode:arabic')],[{'text':'🌐 ترجمة عبر الموقع','url':'https://www.onlinedoctranslator.com/ar/'}],[button('📋 التعليمات','help'),button('🔒 الخصوصية','privacy')],[button('🩺 مراجعة النتيجة','review'),button('⏳ حالة الملف','status')]]}
class Bot:
 def __init__(self,token):
  self.token=token;self.modes={};self.pending=OrderedDict();self.jobs={};self.seen=OrderedDict();self.worker=asyncio.Semaphore(1)
 async def api(self,method,**payload):
  async with self.http.post('https://api.telegram.org/bot'+self.token+'/'+method,json=payload,timeout=aiohttp.ClientTimeout(total=15)) as r:
   result=await r.json()
   if not result.get('ok'):raise RuntimeError('Telegram request failed')
   return result['result']
 async def say(self,chat,text,markup=None):
  return await self.api('sendMessage',chat_id=chat,text=text,reply_markup=markup or menu())
 async def handle(self,u):
  cb=u.get('callback_query');m=(cb.get('message') if cb else u.get('message')) or {}
  if cb:await self.api('answerCallbackQuery',callback_query_id=cb['id'])
  if m.get('chat',{}).get('type')!='private':return
  chat=m['chat']['id'];action=cb.get('data','') if cb else (m.get('text') or '').split(' ')[0].split('@')[0].lstrip('/')
  if action.startswith('mode:'):
   mode=action.split(':')[1]
   if mode not in LABELS:return
   self.modes[chat]=mode
   if len(self.modes)>5000:self.modes.pop(next(iter(self.modes)))
   return await self.say(chat,LABELS[mode]+'\nأرسل الآن ملف PDF نصيًا. اقرأ /privacy قبل الإرسال؛ لا ترسل بيانات مرضى تعريفية.')
  if action.startswith('file:'):
   parts=action.split(':')
   if len(parts)!=3 or parts[2] not in LABELS:return
   item=self.pending.get(parts[1])
   if not item or item['chat']!=chat or time.monotonic()-item['time']>1800:
    return await self.say(chat,'انتهت صلاحية اختيار الملف أو أعيد تشغيل الخدمة. أرسل الملف مجددًا.')
   if chat in self.jobs:return await self.say(chat,'لديك ملف قيد المعالجة. انتظر وصوله أو استخدم /cancel.')
   if len(self.jobs)>=4:return await self.say(chat,'الخدمة مشغولة حاليًا. حاول بعد انتهاء الملفات الحالية.')
   if not os.getenv('GEMINI_API_KEY'):return await self.say(chat,'خدمة الترجمة غير مهيأة بعد؛ تواصل مع المسؤول.')
   await self.say(chat,'⏳ استلمت طلبك: '+LABELS[parts[2]]+'\nسأرسل النتيجة هنا. قد تستغرق المعالجة عدة دقائق. /cancel للإلغاء.')
   self.pending.pop(parts[1],None)
   task=asyncio.create_task(self.job(chat,item['doc'],parts[2]));self.jobs[chat]=task
   return
  if action=='cancel':
   task=self.jobs.get(chat)
   if task:task.cancel();await self.say(chat,'أُرسل طلب الإلغاء. لن يُرسل ملف جديد بعد تأكيد انتهاء المعالجة.')
   else:await self.say(chat,'لا يوجد ملف قيد المعالجة.')
   return
  if action=='status':return await self.say(chat,'⏳ ملفك قيد المعالجة أو ينتظر دوره.' if chat in self.jobs else '✅ جاهز لاستلام ملف جديد. اختر طريقة الترجمة.')
  if m.get('document') and not cb:
   d=m['document']
   if not str(d.get('file_name','')).lower().endswith('.pdf'):return await self.say(chat,'أرسل ملف PDF. Word والصور ليست مدعومة في الإصدار الحالي.')
   if not isinstance(d.get('file_size'),int) or d['file_size']>MAX_BYTES:return await self.say(chat,'الحد الحالي 20 MB لكل ملف. قسّمه إلى أجزاء أصغر.')
   if chat in self.jobs:return await self.say(chat,'انتظر انتهاء ملفك الحالي أو استخدم /cancel.')
   for key,item in list(self.pending.items()):
    if item['chat']==chat or time.monotonic()-item['time']>1800:self.pending.pop(key,None)
   nonce=secrets.token_hex(6);self.pending[nonce]={'chat':chat,'doc':d,'time':time.monotonic()}
   while len(self.pending)>128:self.pending.popitem(last=False)
   preferred=self.modes.get(chat)
   rows=[[button(LABELS[x]+(' ✓' if preferred==x else ''),f'file:{nonce}:{x}')] for x in LABELS]
   rows.append([{'text':'🌐 استخدام موقع الترجمة بدل البوت','url':'https://www.onlinedoctranslator.com/ar/'}])
   rows.append([button('🔒 سياسة المعالجة','privacy')])
   return await self.say(chat,'📄 '+str(d.get('file_name','PDF'))[:150]+'\nاختر طريقة ترجمة هذا الملف.\n\nبالاختيار تؤكد أن الملف خالٍ من بيانات المرضى التعريفية وتوافق على إرساله إلى Gemini وفق /privacy.',{'inline_keyboard':rows})
  texts={'start':WELCOME,'help':HELP,'privacy':PRIVACY,'review':REVIEW,'about':WELCOME,'buy':'الخدمة مجانية. لا نجوم أو باقات.\n\n'+WELCOME}
  await self.say(chat,texts.get(action,WELCOME))
 async def job(self,chat,document,mode):
  try:
   async with asyncio.timeout(900):
    async with self.worker:
     info=await self.api('getFile',file_id=document['file_id'])
     if info.get('file_size',0)>MAX_BYTES:raise TranslationError('حجم الملف أكبر من 20 MB.')
     async with self.http.get('https://api.telegram.org/file/bot'+self.token+'/'+info['file_path'],timeout=aiohttp.ClientTimeout(total=90)) as r:
      if r.status!=200:raise TranslationError('تعذر تنزيل الملف من Telegram؛ أرسله مجددًا.')
      data=bytearray()
      async for chunk in r.content.iter_chunked(65536):
       data.extend(chunk)
       if len(data)>MAX_BYTES:raise TranslationError('الملف أكبر من الحد الحالي 20 MB.')
     result=await process(self.http,os.environ['GEMINI_API_KEY'],bytes(data),mode)
     form=aiohttp.FormData();form.add_field('chat_id',str(chat));form.add_field('caption',LABELS[mode]+'\nفُحص ترتيب المقاطع والأرقام والرموز الأساسية. راجع الدقة الطبية مقابل الأصل. /review')
     form.add_field('document',result,filename='QMR_'+mode+'.pdf',content_type='application/pdf')
     async with self.http.post('https://api.telegram.org/bot'+self.token+'/sendDocument',data=form,timeout=aiohttp.ClientTimeout(total=90)) as r:
      response=await r.json()
      if not response.get('ok'):raise TranslationError('اكتملت الترجمة لكن تعذر إرسال الملف. أعد المحاولة.')
     await self.say(chat,'✅ أرسلت النتيجة. يمكنك إرسال ملف جديد أو اختيار وضع آخر.')
  except asyncio.CancelledError:
   await self.say(chat,'أُلغيت المعالجة. يمكنك إرسال ملف جديد.');raise
  except TranslationError as e:await self.say(chat,'⚠️ '+str(e))
  except asyncio.TimeoutError:await self.say(chat,'انتهت مهلة المعالجة. جرّب ملفًا أصغر أو حاول لاحقًا.')
  except Exception as e:
   logging.warning('Translation job failed: %s',type(e).__name__)
   try:await self.say(chat,'تعذر إكمال المعالجة. أرسل الملف مجددًا لاحقًا.')
   except Exception:pass
  finally:self.jobs.pop(chat,None)
 async def run(self):
  secret=os.environ['WEBHOOK_SECRET'];url=os.environ['RENDER_EXTERNAL_URL'].rstrip('/')
  if len(secret)<32 or not url.startswith('https://'):raise ValueError('Invalid webhook configuration')
  app=web.Application(client_max_size=1024*1024);ready=False
  async def health(request):return web.json_response({'ok':ready,'mode':'document-translation','version':'2.0'},status=200 if ready else 503)
  async def webhook(request):
   if not hmac.compare_digest(request.headers.get('X-Telegram-Bot-Api-Secret-Token',''),secret):raise web.HTTPUnauthorized()
   try:u=await request.json()
   except (ValueError,TypeError):raise web.HTTPBadRequest()
   if not isinstance(u,dict):raise web.HTTPBadRequest()
   uid=u.get('update_id')
   if isinstance(uid,int) and uid in self.seen:return web.json_response({'ok':True})
   if isinstance(uid,int):
    self.seen[uid]=None
    while len(self.seen)>2000:self.seen.popitem(last=False)
   try:await self.handle(u)
   except Exception as e:
    if isinstance(uid,int):self.seen.pop(uid,None)
    logging.warning('Webhook failed: %s',type(e).__name__);raise web.HTTPServiceUnavailable()
   return web.json_response({'ok':True})
  app.router.add_get('/',health);app.router.add_get('/health',health);app.router.add_post('/telegram',webhook)
  runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'0.0.0.0',int(os.getenv('PORT','8080'))).start()
  try:
   async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as self.http:
    await self.api('getMe')
    await self.api('setMyCommands',commands=[{'command':a,'description':b} for a,b in [('start','اختيار طريقة الترجمة'),('help','الملفات المدعومة والتعليمات'),('privacy','خصوصية معالجة الملفات'),('review','مراجعة الدقة الطبية'),('status','حالة الملف'),('cancel','إلغاء المعالجة')]])
    await self.api('setMyDescription',description='QMR Translate: ترجمة PDF النصي داخل Telegram. اختر ترجمة سطرية أو عربية كاملة. مجاني ضمن حدود الخدمة. لا ترسل بيانات مرضى تعريفية.')
    await self.api('setWebhook',url=url+'/telegram',secret_token=secret,allowed_updates=['message','callback_query'],max_connections=5)
    ready=True;await asyncio.Event().wait()
  finally:
   for task in list(self.jobs.values()):task.cancel()
   await asyncio.gather(*list(self.jobs.values()),return_exceptions=True)
   await runner.cleanup()
if __name__=='__main__':asyncio.run(Bot(os.environ['BOT_TOKEN']).run())
