from TheManagement.globalvars import verif_servers

async def verification(message,client):
  if message.server.id in verif_servers:
    await client.send_message(message.channel, 'Custom email verification disabled for this server')
    verif_servers.remove(message.server.id)
  else:
    await client.send_message(message.channel, 'Custom email verification enabled for this server. New members will be asked for email verification.')
    verif_servers.append(message.server.id)