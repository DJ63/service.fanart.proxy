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
import sys
import xbmc
from threading import Thread
from sqlite3 import dbapi2 as database
from request_handler import RequestHandler
from commoncore import kodi
test = xbmc.__version__.split('.')
is_depricated = True if int(test[1]) < 19  else False


class FanartService():

	def clear_art(self):
		kodi.log("Clearing Bad Art...")
		DB_FILE = kodi.vfs.join("special://database", 'Textures13.db')
		BAD_FILE = kodi.vfs.join(kodi.get_profile(), 'badart.log')
		bad_files = list(set(kodi.vfs.read_file(BAD_FILE).split("\n")))
		with database.connect(DB_FILE, check_same_thread=False) as dbh:
			dbc = dbh.cursor()
			for bad_file in bad_files:
				if not bad_file: continue
				f = kodi.vfs.join(bad_file[0], bad_file) + '.jpg'
				dbc.execute("DELETE FROM texture WHERE cachedurl=?", [f])
				f = kodi.vfs.join("special://thumbnails", f)
				kodi.vfs.rm(f, quiet=True)
		dbh.commit()
		kodi.vfs.write_file(BAD_FILE, '')
	
	def start(self):
		class Monitor(xbmc.Monitor):
			def onSettingsChanged(self):
				pass
		monitor = Monitor()
		kodi.log("Service Starting...")
		self.clear_art()
		if kodi.get_setting('enable_fanart_proxy') == 'true':
			CONTROL_PORT = int(kodi.get_setting('control_port'))
			if kodi.get_setting('network_bind') == 'Localhost':
				address = "127.0.0.1"
			else:
				address = "0.0.0.0"
			CONTROL_PROTO = kodi.get_setting('control_protocol')
			kodi.log("Launching Fanart WebInterface on: %s://%s:%s" % (CONTROL_PROTO, address, CONTROL_PORT))
			kodi.log("Verify at: %s://%s:%s/api/up" % (CONTROL_PROTO, address, CONTROL_PORT))
			try:
				if CONTROL_PROTO == 'https':
					from commoncore.webservice import HttpsServer
					certfile = kodi.vfs.join(kodi.get_path(), "resources/server.pem")
					self.httpd = HttpsServer(address, CONTROL_PORT, certfile, RequestHandler)
					self.webserver = Thread(target=self.httpd.serve_forever)
				else:
					from commoncore.webservice import HttpServer
					self.httpd = HttpServer(address, CONTROL_PORT, RequestHandler)
					self.webserver = Thread(target=self.httpd.serve_forever)
			except Exception, e:
				kodi.log(e)
				kodi.raise_error("Service Error: ", str(e))
				sys.exit()
			
			self.webserver.start()
		if is_depricated:
			while not xbmc.abortRequested:
				kodi.sleep(1000)
		else:
			while not monitor.abortRequested():
				if monitor.waitForAbort(1):
					break
	
		self.shutdown()
	
	
	def shutdown(self):
		self.httpd.shutdown()
		self.httpd.socket.close()
		kodi.log("Service Stopping...")


if __name__ == '__main__':
	server = FanartService()
	server.start()
	
		
		
		
