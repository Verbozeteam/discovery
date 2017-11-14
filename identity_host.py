from discovery import DiscoveryServer
import argparse

def WriteIdentity():
    with open("identity", "w") as f:
        for d in mydesc:
            f.write(str(d[0]) + "\n")
            f.write(d[1] + "\n")
        f.close()
mydesc = [(3, "New Room")]
try:
    with open("identity", "r") as f:
        content = f.readlines()
        content = list(map(lambda x: x[:-1] if x[-1] == "\n" else x, content))
        if len(content) == 0 or len(content) % 2 != 0:
            raise
        mydesc = []
        for i in range(0, len(content), 2):
            mydesc += [(int(content[i]), str(content[i+1]))]
except:
    WriteIdentity()

print ("Identity: {}".format(str(mydesc)))

server = DiscoveryServer(identities=mydesc)
server.run()
