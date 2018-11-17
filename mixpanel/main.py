import asyncio
import aiohttp
from time import time
import base64
import ujson
import urllib
from band import logger, settings, expose, worker
from .helpers import flatten_dict, prefixer

state = dict(buffer=[])


@expose.listener()
async def broadcast(**params):
    project_id = params.get('projectId')
    if project_id and project_id in settings.projects:
        key = params.get('key', None)
        if key and key.startswith(settings.key_prefix):
            data = params.pop('data', {})
            masked = prefixer(params)
            data.update(masked)
            flat_data = flatten_dict(data)
            flat_data.update({
                'distinct_id': params.get('uid', None),
                'token': settings.mixpanel_token,
                'time': round(time())
            })
            mp_name = params.get('service', 'none') + '/' + params.get('name', 'none')
            mp_rec = {'event': mp_name, 'properties': flat_data}
            state['buffer'].append(mp_rec)


@worker()
async def uploader():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    if len(state['buffer']):
                        buff = state['buffer']
                        state['buffer'] = []
                        enc = ujson.dumps(buff, ensure_ascii=False)
                        q = urllib.parse.urlencode({
                            'data':
                            base64.encodebytes(enc.encode())
                        })
                        async with session.post(
                                settings.endpoint, data=q) as resp:
                            logger.info(
                                'uploading',
                                items=len(buff),
                                status=resp.status)
                    await asyncio.sleep(1)
            pass
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception('exc')
        await asyncio.sleep(5)
