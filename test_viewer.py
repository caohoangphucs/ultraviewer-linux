import re
import threading
import unittest
import urllib.request
import urllib.error
from viewer import Viewer,make_server


class ViewerTests(unittest.TestCase):
    def test_http_rejects_cross_origin_input(self):
        viewer=Viewer({}, {}, b'')
        server=make_server(viewer,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base) as response:html=response.read().decode()
            token=re.search("const token='([^']+)'",html)[1]
            for headers in [{},{'X-Viewer-Token':token,'Origin':'https://untrusted.example'}]:
                request=urllib.request.Request(base+'/disconnect',data=b'{}',headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code,403)
            request=urllib.request.Request(base+'/disconnect',data=b'{}',headers={'X-Viewer-Token':token})
            with urllib.request.urlopen(request) as response:self.assertEqual(response.status,200)
            self.assertTrue(viewer.stop.is_set())
        finally:server.shutdown();server.server_close();thread.join()

    def test_input_validation_and_closed_session(self):
        viewer=Viewer({}, {}, b'')
        with self.assertRaises(ValueError):viewer.event({'type':'key','vk':65,'down':True})
        viewer.state['state']='connected'
        with self.assertRaises(ValueError):viewer.event({'type':'wheel','delta':40000})
        viewer.event({'type':'key','vk':65,'down':True})
        self.assertEqual(viewer.commands.get_nowait()[0],b'8|||256|||65')


if __name__=='__main__':unittest.main()
