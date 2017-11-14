import socket
import select
import traceback
import netifaces
import time

from collections import defaultdict

# Discovery packet:
# [MAGIC(2) | TYPE(1) | LENGTH(1) | CONTENT(LENGTH)]
# MAGIC: 0x29 0xad
# TYPE: 0 => discovery broadcast
#       1 => set private info (DEPRICATED)
#       2 => master server
#       3 => room controller
#       4 => TV controller
#       5 => camera
#       6 => kitchen

class PROTOCOL:
    MAGIC = bytearray([0x29, 0xad])

    PORT = 7991

    @staticmethod
    def MAKE_PACKET(type, data):
        return PROTOCOL.MAGIC + bytearray([type, len(data)]) + data.encode('UTF-8')

class INTERFACE(object):
    def __init__(self, name, ip="", bcast="", port=-1):
        self.name = name
        self.ip = ip
        self.broadcast = bcast
        self.port = port
        self.socket = None

    def close(self):
        try:
            if self.socket != None:
                self.socket.close()
            self.socket = None
        except:
            pass

    def open(self, is_hosting=False):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if is_hosting:
                self.socket.bind((self.broadcast, self.port))
            return True
        except:
            return False

class DiscoveryServer(object):
    def __init__(self, port=PROTOCOL.PORT, allowed_interfaces=None, identities=[]):
        self.port = port
        self.identities = identities
        self.allowed_interfaces = allowed_interfaces
        self.current_interfaces = {}
        self.buffers = defaultdict(lambda: bytearray([])) # ip -> bytearray buffers of senders
        self.is_hosting = True # sockets opened by this object are hosting sockets (bound)

    def on_device_requested_discovery(self, interface, address, data):
        print("Received broadcast from {}".format(address))
        try:
            for (identity_type, identity_data) in self.identities:
                interface.socket.sendto(PROTOCOL.MAKE_PACKET(identity_type, identity_data), address)
        except Exception as e:
            print (e)
            print (address)

    def on_device_discovered(self, interface, address, type, data):
        pass

    def on_message(self, interface, address, type, data):
        if type == 0: # discovery packet
            self.on_device_requested_discovery(interface, address, data)
        elif type == 1: # set private info (depricated)
            pass
        else:
            self.on_device_discovered(interface, address, type, data)

    def on_input(self, message, address, interface):
        self.buffers[address[0]] += message
        while len(self.buffers[address[0]]) >= 4:
            if self.buffers[address[0]][0:2] == PROTOCOL.MAGIC:
                # seems like the right packet...
                msg_type = int(self.buffers[address[0]][2])
                msg_size = int(self.buffers[address[0]][3])
                if len(self.buffers[address[0]]) >= msg_size + 4:
                    # got the full packet
                    data = self.buffers[address[0]][4:4+msg_size]
                    self.buffers[address[0]] = self.buffers[address[0]][4+msg_size:]
                    try: self.on_message(interface, address, msg_type, data)
                    except: pass
                else: # not ready yet, wait for more input
                    break
            else: # skip a byte
                self.buffers[address[0]] = self.buffers[address[0]][1:]

    def run(self, timeout=-1):
        start_time = time.time()

        while timeout < 0 or time.time() - start_time < timeout:
            self.update_interfaces()

            sockets = self.get_open_sockets()
            try:
                ready_sockets, _, _ = select.select(sockets, [], [], 1)
                for rs in ready_sockets:
                    message, address = rs.recvfrom(1024)
                    iface = list(filter(lambda iface: iface.socket == rs, self.current_interfaces.values()))[0]
                    self.on_input(message, address, iface)
            except KeyboardInterrupt as e:
                break
            except Exception as e:
                print ("Select failed: {}".format(e))

        # clear interfaces
        for iface in self.current_interfaces.values():
            iface.close()
        self.current_interfaces = {}

    def update_interfaces(self):
        ifaces = {}
        if self.is_hosting:
            ifaces = {"generic": INTERFACE("generic", "0.0.0.0", "0.0.0.0", self.port)}
        else:
            for i in netifaces.interfaces():
                if self.allowed_interfaces == None or i in self.allowed_interfaces:
                    try:
                        ip = netifaces.ifaddresses(i)[netifaces.AF_INET][0]['addr']
                        bcast = netifaces.ifaddresses(i)[netifaces.AF_INET][0]['broadcast']
                        ifaces[i] = INTERFACE(i, ip, bcast, self.port)
                    except: pass

        # first check if any interfaces being hosted no longer exists
        for iface in list(self.current_interfaces.keys()):
            if iface not in ifaces:
                self.current_interfaces[iface].close()
                del self.current_interfaces[iface]

        # now check if new interfaces are available
        for iface in list(ifaces.keys()):
            if iface not in self.current_interfaces:
                if ifaces[iface].open(is_hosting=self.is_hosting):
                    self.current_interfaces[iface] = ifaces[iface]
                    self.on_interface_added(ifaces[iface])

    def get_open_sockets(self):
        return list(map(lambda hi: hi.socket, self.current_interfaces.values()))

    def on_interface_added(self, interface):
        pass

class DiscoveryRequest(DiscoveryServer):
    def __init__(self, port=PROTOCOL.PORT, allowed_interfaces=None):
        super(DiscoveryRequest, self).__init__(port=port, allowed_interfaces=allowed_interfaces)
        self.is_hosting = False

    def on_device_discovered(self, interface, address, type, data):
        print("Found device on {} [type={}][data={}]".format(address, type, data))

    def on_interface_added(self, interface):
        try:
            print("Sending broadcast on interface {} ({}:{})".format(interface.name, interface.broadcast, interface.port))
            interface.socket.sendto(PROTOCOL.MAKE_PACKET(0, ""), (interface.broadcast, interface.port))
        except: pass


