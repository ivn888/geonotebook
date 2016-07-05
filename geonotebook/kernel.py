from ipykernel.ipkernel import IPythonKernel
import logging
from logging.handlers import SysLogHandler

from inspect import getmembers, ismethod, getargspec
from types import MethodType

class Geonotebook(object):
    msg_types = ['get_protocol', 'set_center', 'set_region']

    _protocol = None
    _remote = None

    class Remote(object):
        def validate(self, protocol, *args, **kwargs):
            assert len(args) == len(protocol["required"]), \
                "Protocol {} has an arity of {}. Called with {}".format(
                    name, len(args), len(self.protocol[name]["required"]))

        @property
        def log(self):
            try:
                return self.notebook._kernel.log
            except:
                return logging

        def _make_protocol_method(self, protocol):
            """Make a method closure based on a protocol definition

            This takes a protocol and generates a closure that accepts
            functions to execute the remote proceedure call.  This closure
            is set on the Notebook _remote object making it possible to do:

            Geonotebook._remote.set_center(-74.25, 40.0, 4)

            which will validate the argumetns and send the message of the
            comm.

            :param protocol: a protocol dict
            :returns: a closure that validates and executes the RPC
            :rtype: MethodType

            """

            def _protocol_closure(self, *args, **kwargs):
                try:
                    self.validate(protocol, *args, **kwargs)
                except Exception as e:
                    # log something here
                    raise e

                self.comm.send(
                    {'msg_type': protocol['proceedure'],
                     'args': args, 'kwargs': kwargs})

            return MethodType(_protocol_closure, self, self.__class__)

        def __init__(self, comm, notebook, protocol):
            self.comm = comm
            self.notebook = notebook
            self.protocol = protocol

            for p in self.protocol:
                assert 'proceedure' in p, \
                    ""
                assert 'required' in p, \
                    ""
                assert 'optional' in p, \
                    ""

                setattr(self, p['proceedure'], self._make_protocol_method(p))


    def __init__(self, kernel, *args, **kwargs):
        self._protocol = None
        self.view_port = None
        self.region = None
        self._kernel = kernel

    @classmethod
    def class_protocol(cls):
        """Initializes the RPC protocol description

        Provides a static, lazy loaded description of the functions that
        are available to be called by the RPC mechanism.

        :param cls: The class (e.g. Geonotebook)
        :returns: the protocol description
        :rtype: dict

        """

        if cls._protocol is None:
            def _method_protocol(fn, method):
                spec = getargspec(method)

                # spec.args[1:] so we don't include 'self'
                params = spec.args[1:]
                # The number of optional arguments
                d = len(spec.defaults) if spec.defaults is not None else 0
                # The number of required arguments
                r = len(params) - d

                # Would be nice to include whether or to expect a reply, or
                # If this is just a notification function
                return {'proceedure': fn,
                        'required': params[:r],
                        'optional': params[r:]}

            cls._protocol = [_method_protocol(fn, method) for fn, method in
                             getmembers(cls, predicate=ismethod) if fn in cls.msg_types]
        return cls._protocol


    def _send_msg(self, msg):
        """Send a message to the client.

        'msg' should be a well formed RPC message.

        :param msg: The RPC message
        :returns: Nothing
        :rtype: None

        """

        self._kernel.comm.send(msg)

    def _recv_msg(self, msg):
        """Recieve an RPC message from the client

        :param msg: An RPC message
        :returns: Nothing
        :rtype: None

        """

        assert 'msg_type' in msg, \
            u"'msg_type' must be defined!"
        assert msg['msg_type'] in self.msg_types, \
            u"'msg_type' must be one of {}".format(",".join(self.msg_types))

    ### RPC endpoints ###

    def set_center(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


    def set_region(self, bounding_box=None):
        pass

    def get_protocol(self):
        return self.__class__.class_protocol()





class GeonotebookKernel(IPythonKernel):
    def _unwrap(self, msg):
        """Unwrap a Comm message

        Remove the Comm envolpe and return an RPC message

        :param msg: the Comm message
        :returns: An RPC message
        :rtype: dict

        """

        return msg['content']['data']

    def handle_comm_msg(self, msg):
        """Handler for incomming comm messages

        :param msg: a Comm message
        :returns: Nothing
        :rtype: None

        """

        try:
            self.geonotebook._recv_msg(self._unwrap(msg))
        except Exception as e:
            self.log.error(u"Error processing msg: {}".format(str(e)))


    def handle_comm_open(self, comm, msg):
        """Handler for opening a comm

        :param comm: The comm to open
        :param msg: The initial comm_open message
        :returns: Nothing
        :rtype: None

        """

        # TODO: msg should contain a protocol definition for the client side
        #       handle comm msg can return a closure that includes the client
        #       side protocol - protocol should be converted to an proxy class
        #       so we can call functions (as promises?)

        # Check if the msg is empty - no protocol - die
        self.geonotebook._remote = self.geonotebook.Remote(comm, self.geonotebook, self._unwrap(msg))
        comm.on_msg(self.handle_comm_msg)


    def __init__(self, **kwargs):
        kwargs['log'].setLevel(logging.DEBUG)

        self.geonotebook = Geonotebook(self)
        super(GeonotebookKernel, self).__init__(**kwargs)


        self.shell.user_ns.update({'M': self.geonotebook})

        self.comm_manager.register_target('geonotebook', self.handle_comm_open)
