"""
MiPAを使用する上でちょっとした際に便利なツール一覧
"""
from __future__ import annotations
import asyncio

import re
from datetime import datetime, timedelta
from inspect import isawaitable
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar
from urllib.parse import urlencode
import uuid

import aiohttp

__all__ = (
    'deprecated_func',
    'MiTime',
    'get_cache_key',
    'key_builder',
    'check_multi_arg',
    'async_all',
    'find',
    'remove_list_empty',
    'remove_dict_empty',
    'upper_to_lower',
    'str_lower',
    'bool_to_string',
)

T = TypeVar('T')


def deprecated_func(func):
    print(f'deprecated function:{func.__name__}')


class MiTime:
    def __init__(self, start: timedelta, end: datetime):
        self.start = start
        self.end = end


class AuthClient:
    """
    Tokenの取得を手助けするクラス
    """
    
    def __init__(
        self,
        instance_uri: str,
        name: str,
        description: str,
        permissions: Optional[List[str]] = None,
        *,
        icon: Optional[str] = None,
        use_miauth: bool = False,
    ):
        """
        Parameters
        ----------
        instance_uri : str
            アプリケーションを作成したいインスタンスのURL
        name : str
            アプリケーションの名前
        description : str
            アプリケーションの説明
        permissions : Optional[List[str]], default=None
            アプリケーションが要求する権限
        icon: Optional[str], default=None
            アプリケーションのアイコン画像URL
        use_miauth: bool, default=False
            MiAuthを使用するか
        """
        
        if permissions is None:
            permissions = ['read:account']
        self.__client_session = aiohttp.ClientSession()
        self.__instance_uri: str = instance_uri
        self.__name: str = name
        self.__description: str = description
        self.__permissions: List[str] = permissions
        self.__icon: Optional[str] = icon
        self.__use_miauth: bool = use_miauth
        self.__session_token: uuid.UUID
        self.__secret: str

    async def get_auth_url(self) -> str:
        """
        認証に使用するURLを取得します
        
        Returns
        -------
        str
            認証に使用するURL
        """
        
        field = remove_dict_empty(
            {
                'name': self.__name,
                'description': self.__description,
                'icon': self.__icon,
            }
        )
        if self.__use_miauth:
            field['permissions'] = self.__permissions
            query = urlencode(field)
            self.__session_token = uuid.uuid4()
            return (
                f'{self.__instance_uri}/miauth/{self.__session_token}?{query}'
            )
        else:
            field['permission'] = self.__permissions
            async with self.__client_session.post(
                f'{self.__instance_uri}/api/app/create', json=field
            ) as res:
                data = await res.json()
                self.__secret = data['secret']
            async with self.__client_session.post(
                f'{self.__instance_uri}/api/auth/session/generate',
                json={'appSecret': self.__secret},
            ) as res:
                data = await res.json()
                self.__session_token = data['token']
                return data['url']

    async def check_auth(self) -> str:
        """
        認証が完了したかを確認し完了している場合はTokenを返します
        
        Returns
        -------
        str
            Token
        """
        
        if self.__use_miauth:
            while True:
                async with self.__client_session.post(
                    f'{self.__instance_uri}/api/miauth/{self.__session_token}/check'
                ) as res:
                    data = await res.json()
                    if data.get('ok') is True:
                        break
                await asyncio.sleep(1)
        else:
            while True:
                async with self.__client_session.post(
                    f'{self.__instance_uri}/api/auth/session/userkey',
                    json={
                        'appSecret': self.__secret,
                        'token': self.__session_token,
                    },
                ) as res:
                    data = await res.json()
                    if data.get('error', {}).get('code') != 'PENDING_SESSION':
                        break
                await asyncio.sleep(1)
        await self.__client_session.close()
        return data['token'] if self.__use_miauth else data['accessToken']


def get_cache_key(func):
    async def decorator(self, *args, **kwargs):
        ordered_kwargs = sorted(kwargs.items())
        key = (
            (func.__module__ or '')
            + '.{0}'
            + f'{self}'
            + str(args)
            + str(ordered_kwargs)
        )
        return await func(self, *args, **kwargs, cache_key=key)

    return decorator


def key_builder(func, cls, *args, **kwargs):
    ordered_kwargs = sorted(kwargs.items())
    key = (
        (func.__module__ or '')
        + f'.{func.__name__}'
        + f'{cls}'
        + str(args)
        + str(ordered_kwargs)
    )
    return key


def check_multi_arg(*args: Any) -> bool:
    """
    複数の値を受け取り値が存在するかをboolで返します

    Parameters
    ----------
    args : list
        確認したい変数のリスト

    Returns
    -------
    bool
        存在する場合はTrue, 存在しない場合はFalse
    """
    return bool([i for i in args if i])


async def async_all(gen, *, check=isawaitable):
    for elem in gen:
        if check(elem):
            elem = await elem
        if not elem:
            return False
    return True


def find(predicate: Callable[[T], Any], seq: Iterable[T]) -> Optional[T]:
    """A helper to return the first element found in the sequence
    that meets the predicate. For example: ::

        member = discord.utils.find(lambda m: m.name == 'Mighty', channel.guild.members)

    would find the first :class:`~discord.Member` whose name is 'Mighty' and return it.
    If an entry is not found, then ``None`` is returned.

    This is different from :func:`py:filter` due to the fact it stops the moment it finds
    a valid entry.

    Parameters
    -----------
    predicate
        A function that returns a boolean-like result.
    seq: :class:`collections.abc.Iterable`
        The iterable to search through.
    """
    for element in seq:
        if predicate(element):
            return element
    return None


def remove_list_empty(data: List[Any]) -> List[Any]:
    """
    Parameters
    ----------
    data: dict
        空のkeyを削除したいdict

    Returns
    -------
    Dict[str, Any]
        空のkeyがなくなったdict
    """
    return [k for k in data if k]


def remove_dict_empty(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parameters
    ----------
    data: dict
        空のkeyを削除したいdict

    Returns
    -------
    _data: dict
        空のkeyがなくなったdict
    """

    _data = {}
    _data = {k: v for k, v in data.items() if v is not None}
    _data = {k: v for k, v in data.items() if v}
    return _data


def upper_to_lower(
    data: Dict[str, Any],
    field: Optional[Dict[str, Any]] = None,
    nest: bool = True,
    replace_list: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    data: dict
        小文字にしたいkeyがあるdict
    field: dict, default=None
        謎
    nest: bool, default=True
        ネストされたdictのkeyも小文字にするか否か
    replace_list: dict, default=None
        dictのkey名を特定の物に置き換える

    Returns
    -------
    field : dict
        小文字になった, key名が変更されたdict
    """

    if data is None:
        return {}
    if replace_list is None:
        replace_list = {}

    if field is None:
        field = {}
    for attr in data:
        pattern = re.compile('[A-Z]')
        large = [i.group().lower() for i in pattern.finditer(attr)]
        result = [None] * (len(large + pattern.split(attr)))
        result[::2] = pattern.split(attr)
        result[1::2] = ['_' + i.lower() for i in large]
        default_key = ''.join(result)
        if replace_list.get(attr):
            default_key = default_key.replace(attr, replace_list.get(attr))
        field[default_key] = data[attr]
        if isinstance(field[default_key], dict) and nest:
            field[default_key] = upper_to_lower(field[default_key])
    return field


def str_lower(text: str):
    pattern = re.compile('[A-Z]')
    large = [i.group().lower() for i in pattern.finditer(text)]
    result = [None] * (len(large + pattern.split(text)))
    result[::2] = pattern.split(text)
    result[1::2] = ['_' + i.lower() for i in large]
    return ''.join(result)


def bool_to_string(boolean: bool) -> str:
    """
    boolを小文字にして文字列として返します

    Parameters
    ----------
    boolean : bool
        変更したいbool値
    Returns
    -------
    true or false: str
        小文字になったbool文字列
    """
    return 'true' if boolean else 'false'
