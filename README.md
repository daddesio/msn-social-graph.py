## Overview

**msn-social-graph.py** is a script to generate a social graph from
[MSN Messenger XML](http://chatlogformats.wikia.com/wiki/Microsoft_MSN_XML)
chat logs. This is not strictly a "social graph" in the usual sense, but
rather an **introduction graph**: you added A who introduced you to B
who introduced you to C ...

Great for forensics and/or for anyone who wants to trace back how they
initially met their MSN friends.

This script is licensed under the public domain (see UNLICENSE).

Usage:

```
msn-social-graph.py -i path_to_xml_files -m main_users_email > output.dot
sfdp -x -T png -o output.png output.dot # this will take a few mins
```

Example output for a small contacts list:

![msn_social_graph.py output for 12 contacts](http://daddesio.com/~andrew/files/msn_social_graph/12_contacts.png)

[DOT file for the above graph; 12 contacts](http://daddesio.com/~andrew/files/msn_social_graph/12_contacts.dot)

You can also do a large contacts list, although the output is messy, so
you are better off looking at the raw DOT file (click for full
resolution):

[![msn_social_graph.py output for 393 contacts](http://daddesio.com/~andrew/files/msn_social_graph/393_contacts_thumb.png)](http://daddesio.com/~andrew/files/msn_social_graph/393_contacts.png)

[DOT file for the above graph; 393 contacts](http://daddesio.com/~andrew/files/msn_social_graph/393_contacts.dot)

## How to interpret the graph

Being randomly added to group conversations by one of your friends was
actually one of the main ways of making new friends on MSN. Using the
first group conversation you had with a contact (call him A), this
script tries to place the blame on who is "responsible" for introducing
you to A. Who exactly to blame is a bit of a philosophical question,
especially for very large group conversations (>= 30 people), but this
script assumes we can probably place some blame on the following people:

* (Gray edges): Former contacts who were in the conversation at any
  point.
* (Black edges): Former contacts who were in the conversation at any
  point before A left (perhaps, before A joined as well).
* (Blue edges): Former contacts who were in the conversation when A
  joined, since they may have added A.
* (Green edges): Former contacts who were in the conversation when
  the main user joined, since they may have added the main user.

Here, we use the following definition of "former contact": Person A is a
"former contact" to B if we have chat logs with A that are "older" than
those of B. More specifically:

1. A's first post is older than B's first post; and
2. A's first post and B's first post are in separate conversations.
