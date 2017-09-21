from TheManagement.globalvars import spam_filter

async def spamfilter(message,client):
  if message.channel.id in spam_filter:
    spam_filter.remove(message.channel.id)
    await client.send_message(message.channel, 'Turned off spam filtering for ' + message.channel.mention)
  else:
    spam_filter.append(message.channel.id)
    await client.send_message(message.channel, 'Spam filtering has been enabled for ' + message.channel.mention)
