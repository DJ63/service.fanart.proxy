# -*- coding: utf-8 -*-

'''*
	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <http://www.gnu.org/licenses/>.
*'''

import json
import sys
import cgi
import socket
import hashlib
import datetime
from os import curdir, sep
from urlparse import urlparse
from BaseHTTPServer import BaseHTTPRequestHandler
from commoncore import kodi
from commoncore import core
from commoncore import fanart
from commoncore import trakt
from commoncore.dispatcher import FunctionDispatcher

HOST_ADDRESS = socket.gethostname()
LOG_FILE = kodi.vfs.join(kodi.get_profile(), 'access.log')
BAD_FILE = kodi.vfs.join(kodi.get_profile(), 'badart.log')
kodi.log("Setting Fanart API Access log to: %s" % LOG_FILE)
DEFAULT_POSTER = kodi.vfs.join(kodi.get_path(), 'resources/artwork/no_poster.jpg')
DEFAULT_SCREENSHOT = kodi.vfs.join(kodi.get_path(), 'resources/artwork/no_screenshot.jpg')
DEFAULT_FANART = kodi.vfs.join(kodi.get_path(), 'resources/artwork/no_fanart.jpg')
DEFAULT_PERSON = kodi.vfs.join(kodi.get_path(), 'resources/artwork/no_person.jpg')
client_host = '127.0.0.1'
client_port = kodi.get_setting('control_port', 'service.fanart.proxy')
client_protocol = kodi.get_setting('control_protocol', 'service.fanart.proxy')
BASE_FANART_URL = '%s://%s:%s' % (client_protocol, client_host, client_port) 

def get_crc32( string ):
	string = string.lower()
	bytes = bytearray(string.encode())
	crc = 0xffffffff;
	for b in bytes:
		crc = crc ^ (b << 24)
		for i in range(8):
			if (crc & 0x80000000 ):
				crc = (crc << 1) ^ 0x04C11DB7
			else:
				crc = crc << 1;
		crc = crc & 0xFFFFFFFF
	return '%08x' % crc


class RequestHandler(BaseHTTPRequestHandler):
	kodi_disconnect = False
	log_file = kodi.vfs.open(LOG_FILE, 'w')
	bad_file = kodi.vfs.open(BAD_FILE, 'w')
	
	def process_cgi(self):
		parts = urlparse(self.path)
		path = parts.path
		query = parts.query
		data = cgi.parse_qs(query, keep_blank_values=True)
		arguments = path.split('/')
		return arguments, data, path

	def finish(self,*args,**kw):
		try:
			if not self.wfile.closed:
				self.wfile.flush()
				self.wfile.close()
		except socket.error:
			pass
		self.rfile.close()
	
	def handle(self):
		"""Handles a request ignoring dropped connections."""
		try:
			return BaseHTTPRequestHandler.handle(self)
		except (socket.error, socket.timeout) as e:
			self.connection_dropped(e)

	def connection_dropped(self, error, environ=None):
		self.kodi_disconnect = True
		

	def log_message(self, format, *args):
		self.log_file.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))
	

	def generate_response_headers(self, file_name=None, content_type="application/octet-stream"):
		self._response_headers = {}
		now = datetime.datetime.utcnow()
		self._response_headers['Date'] = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
		self._response_headers['Server'] = 'Fanart Proxy/%s' % kodi.get_version()
		self._response_headers['Last-Modified'] = "Wed, 21 Feb 2000 08:43:39 GMT"
		self._response_headers['Accept-Ranges'] = 'bytes'
		if file_name is not None:
			self._response_headers['ETag'] = hashlib.md5(file_name).hexdigest()
			self._response_headers['Content-Disposition'] = "attachment; filename=\"%s\";" % kodi.vfs.filename(file_name)
			self._response_headers['Content-Length'] = kodi.vfs.get_size(file_name)	
			self._response_headers['Range'] = '0-'
		self._response_headers['Content-Type'] = content_type

			
	
	def set_range_header(self, start_byte, total_bytes):
		if start_byte == 0:
			self._response_headers['Content-Length'] = total_bytes
			self._response_headers['Range'] = '0-'
		else:
			last_byte = total_bytes - 1
			self._response_headers['Range'] = "%s-%s" % (start_byte, last_byte)
			self._response_headers['Content-Range'] = "%s-%s/%s" % (start_byte, last_byte, total_bytes)
			self._response_headers['Content-Length'] = str(total_bytes - start_byte)
		
	def send_all_headers(self, response_code=206):
		self.send_response(response_code)
		for header in self._response_headers:
			self.send_header(header, str(self._response_headers[header]))
		self.end_headers()
	
	def send_error(self, code, message):	
		self.do_Response(content={'status': code, 'message': message})
	
	def not_found(self):
		self.send_response(404)
		self.end_headers()
		self.wfile.flush()
			
	def do_GET(self):
		arguments, data, path = self.process_cgi()
		dispatcher = FunctionDispatcher()
		def send_error():
			self.send_error(500,'Internal Server Error')
		dispatcher.error = send_error
		
		def send_redirect(url):
			if url:
				self.send_response(302)
				self.send_header('Location', url)
				self.end_headers()
				self.wfile.flush()
			else:
				self.send_error(404,'File not found')
			return False	
		
		def send_file(path):
			self.bad_file.write(get_crc32(BASE_FANART_URL + self.path))
			self.bad_file.write("\n")
			self.generate_response_headers(path)
			self.send_all_headers(200)
			self.wfile.write(kodi.vfs.read_file(path, mode='b'))
			self.wfile.flush()

		@dispatcher.register('default')
		def default():
			self.send_error(404,'Endpoint Not Found')
		
		@dispatcher.register('/api/up')
		def up():
			self.do_Response()
		
		@dispatcher.register('/api/metadata/movie')
		def movie_metadata():
			id = data['id'][0] if 'id' in data else None
			id_type = data['id_type'][0] if 'id_type' in data else 'trakt'
			metadata = trakt.get_movie_info(id)
			infolabel = core.make_infolabel('movie', metadata['items'])
			self.do_Response(content={'status': 200, 'metadata': infolabel})
		
		@dispatcher.register('/api/metadata/show')
		def move_metadata():
			id = data['id'][0] if 'id' in data else None
			id_type = data['id_type'][0] if 'id_type' in data else 'trakt'
			metadata = trakt.get_show_info(id)
			infolabel = core.make_infolabel('show', metadata['items'])
			self.do_Response(content={'status': 200, 'metadata': infolabel})
		
		@dispatcher.register('/api/images/movie')
		def movie_images():
			image = data['image'][0] if 'image' in data else ''
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			imdb_id = data['imdb_id'][0] if 'imdb_id' in data else None
			art = fanart.get_movie_art(tmdb_id, imdb_id)
			try:
				if art[image]:
					url = art[image]
				else:
					url = False
			except Exception, e:
				url = False
	
			if url:
				send_redirect(url)
			else:
				if kodi.get_setting('enable_fanart_debug') == 'true':
					kodi.log(art)
				if image == 'poster':
					send_file(DEFAULT_POSTER)
				else:
					send_file(DEFAULT_FANART)
		
		@dispatcher.register('/api/images/show')
		def show_images():
			image = data['image'][0] if 'image' in data else ''
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			tvdb_id = data['tvdb_id'][0] if 'tvdb_id' in data else None
			imdb_id = data['imdb_id'][0] if 'imdb_id' in data else None
			art = fanart.get_show_art(tmdb_id, tvdb_id, imdb_id)
			try:
				if art[image]:
					url = art[image]
				else:
					url = False
			except Exception, e:
				url = False
			if url:
				send_redirect(url)
			else:
				if kodi.get_setting('enable_fanart_debug') == 'true':
					kodi.log(art)
				if image == 'poster':
					send_file(DEFAULT_POSTER)
				else:
					send_file(DEFAULT_FANART)
			
	
		@dispatcher.register('/api/images/episode')
		def episode_images():
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			tvdb_id = data['tvdb_id'][0] if 'tvdb_id' in data else None
			imdb_id = data['imdb_id'][0] if 'imdb_id' in data else None
			season = data['season'][0] if 'season' in data else None
			episode = data['episode'][0] if 'episode' in data else None
			url = fanart.get_episode_art(tmdb_id, tvdb_id, imdb_id, season, episode)
			if url:
				send_redirect(url)
			else:
				send_file(DEFAULT_SCREENSHOT)
			
		@dispatcher.register('/api/images/season')
		def season_images():
			tvdb_id = data['tvdb_id'][0] if 'tvdb_id' in data else None
			season = int(data['season'][0]) if 'season' in data else ''
			art = fanart.get_season_art(tvdb_id, season)
			if art:
				url = art
				send_redirect(url)
			else:
				send_file(DEFAULT_POSTER)
				
		@dispatcher.register('/api/images/person')
		def person_image():
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			url = fanart.get_person_art(tmdb_id)
			if url:
				send_redirect(url)	
			else:
				send_file(DEFAULT_PERSON)
		dispatcher.run(path)
	
	def do_HEAD(self):
		arguments, data, path = self.process_cgi()
		dispatcher = FunctionDispatcher()
		def send_error():
			self.send_error(500,'Internal Server Error')
		dispatcher.error = send_error
				
		def send_redirect(url):
			if url:
				self.send_response(302)
				self.send_header('Location', url)
				self.end_headers()
				self.wfile.flush()
			else:
				self.send_error(404,'File not found')
			return False	
		
		def send_file(path):
			self.bad_file.write(get_crc32(BASE_FANART_URL + self.path))
			self.bad_file.write("\n")
			self.generate_response_headers(path)
			self.send_all_headers(200)
			self.wfile.flush()

		@dispatcher.register('default')
		def default():
			self.send_error(404,'Endpoint Not Found')
		
		@dispatcher.register('/api/up')
		def up():
			self.do_Response()
		
		@dispatcher.register('/api/images/movie')
		def movie_images():
			image = data['image'][0] if 'image' in data else ''
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			imdb_id = data['imdb_id'][0] if 'imdb_id' in data else None
			art = fanart.get_movie_art(tmdb_id, imdb_id)
			try:
				if art[image]:
					url = art[image]
				else:
					url = False
			except Exception, e:
				url = False
	
			if url:
				send_redirect(url)
			else:
				if image == 'poster':
					send_file(DEFAULT_POSTER)
				else:
					send_file(DEFAULT_FANART)
			
		
		@dispatcher.register('/api/images/show')
		def show_images():
			image = data['image'][0] if 'image' in data else ''
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			tvdb_id = data['tvdb_id'][0] if 'tvdb_id' in data else None
			imdb_id = data['imdb_id'][0] if 'imdb_id' in data else None
			art = fanart.get_show_art(tmdb_id, tvdb_id, imdb_id)
			try:
				if art[image]:
					url = art[image]
				else:
					url = False
			except Exception, e:
				url = False
	
			if url:
				send_redirect(url)
			else:
				if image == 'poster':
					send_file(DEFAULT_POSTER)
				else:
					send_file(DEFAULT_FANART)
			
	
		@dispatcher.register('/api/images/episode')
		def episode_images():
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			tvdb_id = data['tvdb_id'][0] if 'tvdb_id' in data else None
			imdb_id = data['imdb_id'][0] if 'imdb_id' in data else None
			season = data['season'][0] if 'season' in data else None
			episode = data['episode'][0] if 'episode' in data else None
			url = fanart.get_episode_art(tmdb_id, tvdb_id, imdb_id, season, episode)
			if url:
				send_redirect(url)
			else:
				send_file(DEFAULT_SCREENSHOT)
			
		@dispatcher.register('/api/images/season')
		def season_images():
			tvdb_id = data['tvdb_id'][0] if 'tvdb_id' in data else None
			season = int(data['season'][0]) if 'season' in data else ''
			art = fanart.get_season_art(tvdb_id, season)
			if art:
				url = art
				send_redirect(url)
			else:
				send_file(DEFAULT_POSTER)
				
		@dispatcher.register('/api/images/person')
		def person_image():
			tmdb_id = data['tmdb_id'][0] if 'tmdb_id' in data else None
			url = fanart.get_person_art(tmdb_id)
			if url:
				send_redirect(url)	
			else:
				send_file(DEFAULT_PERSON)
		dispatcher.run(path)
		
	def do_POST(self):
		self.do_GET()
		
			
	def do_Response(self, content={'status': 200, 'message': 'success'}, content_type='application/json', response_code=200):
		self.generate_response_headers(content_type=content_type)
		self.send_all_headers(response_code)
		if content_type == 'application/json':
			content['host'] = HOST_ADDRESS
			content['debug'] = kodi.get_setting('enable_fanart_debug') == 'true'
			content = json.dumps(content)
		self.wfile.write(content)
		self.wfile.flush()
		self.wfile.close()