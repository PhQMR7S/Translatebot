import asyncio, os, logging, hmac
import aiohttp
from aiohttp import web
SITE="https://www.onlinedoctranslator.com/ar/"
MENU={"inline_keyboard":[[{"text":"🌐 الترجمة المجانية","url":SITE}],[{"text":"📋 التعليمات","callback_data":"help"},{"text":"🔒 الخصوصية","callback_data":"privacy"}]]}
WELCOME="مِداد الطبي 🩺\nخدمة إرشاد مجانية لترجمة الملفات عبر Online Doc Translator. افتح الموقع وارفع الملف واختر العربية ثم نزّل النتيجة. البوت لا يترجم تلقائيًا. لا نجوم أو باقات أو حدود شراء. حدود الموقع مستقلة."
HELP="افتح الموقع من الزر، ارفع المستند الإنجليزي واختر العربية ثم نزّل الملف المترجم. راجع الأرقام والجرعات والمصطلحات مقابل الأصل؛ الترجمة آلية وليست تدقيقًا طبيًا متخصصًا."
PRIVACY="البوت لا ينزّل محتوى الملفات. الرسائل تخضع لسياسة Telegram، والملفات التي ترفعها للموقع تخضع لسياسة الموقع. لا ترسل بيانات مرضى تعريفية. البوت مستقل عن موقع الترجمة."
class Bot:
 def __init__(self, token): self.token=token
 async def api(self,method,**payload):
  async with self.http.post("https://api.telegram.org/bot"+self.token+"/"+method,json=payload) as r:
   result=await r.json()
   if not result.get("ok"): raise RuntimeError("Telegram request failed")
   return result["result"]
 async def handle(self,u):
  cb=u.get("callback_query");m=u.get("message",{})
  if cb:
   await self.api("answerCallbackQuery",callback_query_id=cb["id"])
   m=cb.get("message",{});action=cb.get("data","")
  else: action=m.get("text","").split(" ")[0].split("@")[0].lstrip("/")
  if m.get("chat",{}).get("type")!="private": return
  if m.get("document"): text="📄 افتح الموقع وارفع هذا الملف هناك. البوت لا يعالج الملفات تلقائيًا عبر الموقع."
  elif action in {"privacy","terms"}: text=PRIVACY
  elif action=="help": text=HELP
  elif action in {"buy","shop","paysupport","status","balance"}: text="أُلغيت المدفوعات والباقات. الخدمة مجانية؛ افتح الموقع أدناه."
  else: text=WELCOME
  await self.api("sendMessage",chat_id=m["chat"]["id"],text=text,reply_markup=MENU)
 async def run(self):
  secret=os.environ['WEBHOOK_SECRET']
  if len(secret)<32: raise ValueError('Webhook secret too short')
  url=os.environ['RENDER_EXTERNAL_URL'].rstrip('/')
  if not url.startswith('https://'): raise ValueError('HTTPS required')
  app=web.Application(client_max_size=1024*1024)
  ready=False
  async def health(request): return web.json_response({'ok':ready,'mode':'free-guide'},status=200 if ready else 503)
  async def webhook(request):
   if not hmac.compare_digest(request.headers.get('X-Telegram-Bot-Api-Secret-Token',''),secret): raise web.HTTPUnauthorized()
   try: update=await request.json()
   except (ValueError,TypeError): raise web.HTTPBadRequest()
   if not isinstance(update,dict): raise web.HTTPBadRequest()
   try: await self.handle(update)
   except Exception as e:
    logging.warning('Webhook failed: %s',type(e).__name__)
    raise web.HTTPServiceUnavailable()
   return web.json_response({'ok':True})
  app.router.add_get('/',health);app.router.add_get('/health',health);app.router.add_post('/telegram',webhook)
  runner=web.AppRunner(app);await runner.setup()
  await web.TCPSite(runner,'0.0.0.0',int(os.getenv('PORT','8080'))).start()
  try:
   async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as self.http:
    await self.api('getMe')
    await self.api('setMyCommands',commands=[{'command':x,'description':y} for x,y in [('start','الترجمة المجانية'),('help','التعليمات'),('privacy','الخصوصية')]])
    await self.api('setMyDescription',description='مِداد الطبي: إرشاد مجاني لترجمة المستندات عبر Online Doc Translator. افتح الموقع وارفع الملف هناك. البوت لا يترجم الملفات تلقائيًا ولا يبيع خدمات.')
    await self.api('setWebhook',url=url+'/telegram',secret_token=secret,allowed_updates=['message','callback_query'],max_connections=5)
    ready=True
    await asyncio.Event().wait()
  finally: await runner.cleanup()
if __name__=='__main__': asyncio.run(Bot(os.environ['BOT_TOKEN']).run())
