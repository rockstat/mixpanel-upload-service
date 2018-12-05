import asyncio
import aiohttp
from time import time
import base64
import ujson
import urllib
from band import logger, settings, expose, worker
from band.config import environ
from .helpers import flatten_dict, prefixer

mp_token_prefix = 'MP_TOKEN_'
mp_keys_prefix = 'MP_KEYS_'


class state:
    buffer = []
    # loading MP_TOKEN_* env variables
    mp_tokens = {
        k[len(mp_token_prefix):]: v
        for k, v in environ.items() if k.startswith(mp_token_prefix)
    }
    mp_keys = {
        k[len(mp_keys_prefix):]: v
        for k, v in environ.items() if k.startswith(mp_keys_prefix)
    }


@expose.listener()
async def broadcast(**params):
    project_id = params.get('projectId')
    if project_id:
        project_id = str(project_id)
        if project_id in state.mp_tokens and project_id in state.mp_keys:
            mp_token = state.mp_tokens[project_id]
            key = params.get('key', None)
            if key and key.startswith(state.mp_keys[project_id]):
                push(params, mp_token)


def push(params, mp_token):
    data = params.pop('data', {})
    masked = prefixer(params)
    data.update(masked)
    flat_data = flatten_dict(data)
    flat_data.update({
        'distinct_id': params.get('uid', None),
        'token': mp_token,
        'time': round(time())
    })
    mp_name = params.get('service', 'none') + '/' + params.get('name', 'none')
    mp_rec = {'event': mp_name, 'properties': flat_data}
    state.buffer.append(mp_rec)


@worker()
async def uploader():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    if len(state.buffer):
                        buff = state.buffer.copy()
                        state.buffer.clear()
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
