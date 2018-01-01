#!/usr/bin/env python3
# msn-social-graph.py
# Authors: Andrew D'Addesio
# License: Public domain
# Website: https://github.com/daddesio/msn-social-graph.py
# Usage:
#     msn-social-graph.py -i path_to_xml_files -m main_users_email > output.dot
#     sfdp -x -T png -o output.png output.dot # this will take a few mins
#
# Generate a social graph from MSN Messenger XML chat logs.
#     Note: This is not strictly a "social graph" in the usual sense,
#     but rather an "introduction graph": you added A who introduced you
#     to B who introduced you to C ...
#
#     Color codes for edges (arrows):
#     * Gray:  This person was in the conversation at any point.
#     * Blue:  This person was in the conversation when A joined.
#     * Green: This person was in the conversation when the main user
#              joined.
#
#     Note that edges will only be drawn from former contacts, whose
#     chat logs start earlier than those of A.

from __future__ import print_function
import argparse
import collections
import glob
import os
import re
import sys
from lxml import etree

import sys

# see: https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# A function to filter out Unicode characters.
# Not currently used for anything, but since we're dealing with
# MSN chat logs, you will *definitely* need this function when
# printing out people's crazy usernames to the terminal.
def utf8toascii(str):
    ret = ''
    for c in str:
        if (c >= ' ' and c <= '~') or c == '\t':
            ret += c
        elif c != '\r':
            ret += '?'
    return ret

parser = argparse.ArgumentParser()
parser.add_argument('-i', '--inDir', type=str, required=True,
                    help="location of MSN chat logs (in XML format)")
parser.add_argument('-m', '--mainUsersEmail', type=str, required=True,
                    help="main user's email")
args = parser.parse_args()

try:
    os.chdir(args.inDir)
except OSError:
    eprint("error: failed to change to directory '%s'" % args.inDir)
    sys.exit(1)

# contacts: a global list of all contacts by email address (mapping from
#           email -> Contact)
contacts = collections.OrderedDict()

# posts: a global list of all important posts (across all logs), and
#        which sessions they appear in (mapping from post -> Session[])
posts = {}

def addGlobalPost(post, session):
    if post in posts:
        posts[post].append(session)
    else:
        posts[post] = [session]

# edges: a global list of all edges on the graph
Edge = collections.namedtuple('Edge', ['src', 'dest', 'color'])
edges = []

class Session:
    def __init__(self, id, contact):
        self.id = id
        self.contact = contact
        self.posts = []

    # also adds to the global post list! (i.e. it calls addGlobalPost)
    def addPost(self, post):
        if len(self.posts) > 0 and post <= self.posts[-1]:
            eprint("warning: non-monotonic timestamp: %s <= %s; dropping post"
                   % (post, self.posts[len(self.posts)-1]))
            return

        self.posts.append(post)
        addGlobalPost(post, self)

class Contact:
    def __init__(self, email):
        self.email = email
        self.sessions = []

    def reserveSessions(self, sessionCount):
        # reserve space for "sessionCount" sessions
        for sessionId in range(len(self.sessions)+1, sessionCount+1):
            self.sessions.append(Session(sessionId, self))

    def getSession(self, sessionId):
        return self.sessions[sessionId-1]

    def isFormerContactTo(self, other):
        # Person A is a "former contact" to B if we have chat logs with
        # A that are "older" than those of B. More specifically:
        # 1. A's first post is older than B's first post; and
        # 2. A's first post and B's first post are in separate
        #    conversations.
        myFirstPost = self.getSession(1).posts[0]
        hisFirstPost = other.getSession(1).posts[0]
        if myFirstPost >= hisFirstPost:
            return False

        myFirstConvo = buildConversationByPost(myFirstPost)
        hisFirstConvo = buildConversationByPost(hisFirstPost)
        return (myFirstConvo.firstPost < hisFirstConvo.firstPost)

Participant = collections.namedtuple('Participant', ['email', 'firstPost', 'lastPost'])

class Conversation:
    def __init__(self, participants):
        # participants: An array of (email, firstPost, lastPost) triples
        self.participants = participants

        # precompute the first and last post in the conversation
        self.firstPost = min(participants, key = lambda par: par.firstPost).firstPost
        self.lastPost = max(participants, key = lambda par: par.lastPost).lastPost

# Interval = collections.namedtuple('Interval', ['firstPost', 'lastPost'])
# We don't want to use a namedtuple, since namedtuples are immutable,
# and we need to be able to update the lastPost field.
class Interval:
    def __init__(self, firstPost, lastPost):
        self.firstPost = firstPost
        self.lastPost = lastPost

def buildConversationByPost(post):
    # intervals: a list of all contacts in the conversation and
    # their intervals (a mapping from contact -> Interval)
    intervals = collections.OrderedDict()

    # walk backwards to find the earliest person in the conversation
    sessionA = posts[post][0]
    while True:
        # Go to the person who has this post in his session and also
        # has the longest-running session (oldest first post). If his
        # session doesn't go any further back in time than ours, then
        # we're done.
        firstPostA = sessionA.posts[0]
        nextSessionA = min(posts[firstPostA], key = lambda session: session.posts[0])
        if nextSessionA.posts[0] >= firstPostA:
            break
        sessionA = nextSessionA

    prevPresentContacts = set()
    warnedContacts = set()
    prevPost = None

    # Walk forwards through the session, one post at a time, capturing
    # who has entered/left the session at each post (judging by whether
    # they have that post in their session), until we reach the end of
    # this person's session. Then go to the next person's session.
    while True:
        for p in sessionA.posts:
            if prevPost and p <= prevPost:
                continue

            presentContacts = set()
            for sessionB in posts[p]:
                presentContacts.add(sessionB.contact)

            addedContacts = presentContacts - prevPresentContacts
            deletedContacts = prevPresentContacts - presentContacts

            for contactB in addedContacts:
                if contactB in intervals:
                    # We already have an interval for B. This means
                    # B left the conversation earlier and re-entered.
                    # This is unsupported.
                    if not (contactB in warnedContacts):
                        eprint(("warning: %s left and re-entered the conversation. This is"
                                + " unsupported; all posts by this user after re-entering"
                                + " will be ignored.") % contactB.email)
                        warnedContacts.add(contactB)
                    continue

                # Create an interval for this new contact, but leave
                # the lastPost undefined until he gets deleted.
                intervals[contactB] = Interval(p, None)

            for contactB in deletedContacts:
                interval = intervals[contactB]
                if interval.lastPost == None:
                    interval.lastPost = prevPost

            prevPost = p
            prevPresentContacts = presentContacts

        # Go to the person who has this post in his session and also
        # has the longest-running session (newest last post). If his
        # session doesn't go any farther into the future than ours, then
        # we're done.
        nextSessionA = max(posts[prevPost], key = lambda session: session.posts[-1])
        if nextSessionA.posts[-1] <= sessionA.posts[-1]:
            break
        sessionA = nextSessionA

    # Finally, for everyone who stuck around in the conversation to the
    # end, delete them from the conversation (i.e. set their lastPost).
    for contact, interval in intervals.items():
        if interval.lastPost == None:
            interval.lastPost = prevPost

    # Convert "intervals" from a contact -> (firstPost, lastPost) map
    # to an array of (email, firstPost, lastPost) triples to pass to
    # the Conversation constructor.
    participants = []
    for contact, interval in intervals.items():
        participants.append(Participant(contact.email, interval.firstPost, interval.lastPost))

    return Conversation(participants)

# Read in all the XML files into memory. We actually do not need 99% of
# the information from the files. In particular:
#
# 1. We only care about the timestamp of each post, not the text
#    contents or the sender/recipient information. Since the timestamp
#    has millisecond resolution, we will use the timestamp to
#    mostly-uniquely(*) identify the post's presence inside multiple
#    chatlogs.
#
#    (*) The timestamp is sometimes not unique. Even though the
#    timestamp has millisecond resolution, I've seen several cases
#    (4 in my own chatlogs) where two posts occur at the same
#    millisecond and have the same timestamp. The biggest issue that
#    can result is if a person's chatlog ends at the exact same
#    timestamp of a post in another, unrelated conversation which lasts
#    longer than the real conversation. In that case, this script will
#    incorrectly traverse into that conversation. The odds of all of the
#    above happening are very slim and have not happened in my own
#    chatlogs, so I decided not to add the extra complexity to
#    detect/handle this issue. If a solution is necessary, the cleanest
#    solution would probably be to edit the offending files by hand to
#    have unique timestamps.
#
#    Also, the timestamp is not always monotonically increasing, due to
#    backwards clock adjustments (e.g. NTP, or DST changeover). In my
#    chatlogs, I have 6 instances of backwards clock adjustments:
#    2 due to DST and the rest due to NTP. As long as the DST changeover
#    (and NTP) don't occur in your first conversation with a contact,
#    you're fine.
#
#    Relevant xkcd: https://xkcd.com/1883/
#
# 2. We only care about the following "special" posts in a conversation:
#    (*) The first post of the session
#    (*) The post that follows a Join post
#    (*) The post that precedes a Leave post
#    (*) The last post of the session
#
#    With just the above posts, we have enough information to
#    reconstruct the interval graph of all participants in the
#    conversation.
for filename in os.listdir('.'):
    match = re.match("^([^ ]+).*\\.xml$", filename, re.IGNORECASE)
    if not match:
        continue

    email = match.group(1)
    eprint("reading %s" % filename)

    if not (email in contacts):
        contacts[email] = Contact(email)
    contact = contacts[email]

    prevTag = None
    prevPost = None
    prevSessionId = None

    for action, elem in etree.iterparse(filename, encoding='utf-8', events=["start"]):
        tag = elem.tag

        if tag == 'Log':
            # pre-allocate one Session object per session in the XML file
            lastSessionId = int(elem.attrib['LastSessionID'])
            contact.reserveSessions(lastSessionId)
            continue

        if (tag != 'Join' and tag != 'Message' and tag != 'Leave'
            and tag != 'Invitation' and tag != 'InvitatationResponse'):
            continue

        sessionId = int(elem.attrib['SessionID'])
        post = elem.attrib['DateTime']
        # eprint("%s:%s:%s" % (elem.tag, post, sessionId))

        # If we receive a Leave post, or this post starts a new session,
        # save the previous post.
        if prevPost and (tag == 'Leave' or sessionId != prevSessionId):
            contact.getSession(prevSessionId).addPost(prevPost)

        # If the previous post was a Join post, or if this post starts a
        # new session, save this post.
        if prevTag == 'Join' or sessionId != prevSessionId:
            contact.getSession(sessionId).addPost(post)
            # make sure we don't save this post twice
            post = None

        prevTag = tag
        prevPost = post
        prevSessionId = sessionId

    # Save the final post of the final session.
    if prevPost:
        contact.getSession(prevSessionId).addPost(prevPost)

# It's possible the first XML file for a contact was deleted, so
# we don't have the first conversation (SessionID=1) with that
# person in our logs. In that case, let's assume we had a 1-on-1
# conversation with him long ago in the past.
blankConvoCounter = 0
for email, contact in contacts.items():
    if len(contact.getSession(1).posts) == 0:
        eprint(("warning: Failed to locate the first message (SessionID=1) with %s;"
                + " as such, we must generate a blank conversation for this user."
                + " Are you missing an XML file?") % email)
        post = "0000-%010d" % blankConvoCounter
        contact.getSession(1).addPost(post)
        blankConvoCounter += 1

for emailA, contactA in contacts.items():
    eprint("calculating incoming edges for %s" % emailA)
    firstPostA = contactA.getSession(1).posts[0]
    lastPostA = contactA.getSession(1).posts[-1]
    eprint("* first message with this user starts at time %s" % firstPostA)
    eprint("* rebuilding conversation...")
    convo = buildConversationByPost(firstPostA)
    eprint("* done. conversation appears to span from %s to %s and has %d participants."
           % (convo.firstPost, convo.lastPost, len(convo.participants)))

    num_edges = 0

    for emailB, firstPostB, lastPostB in convo.participants:
        # Do not draw an edge if B is not a former contact to A.
        contactB = contacts[emailB]
        if not contactB.isFormerContactTo(contactA):
            continue

        color = 'gray'

        # If B joined the conversation before A left,
        # recolor his edge to black.
        if firstPostB <= lastPostA:
            color = 'black'

        # If B was in the conversation when A entered,
        # recolor his edge to blue.
        if firstPostB <= firstPostA and lastPostB >= firstPostA:
            color = 'blue'

        # If B was in the conversation when the conversation started
        # (or the main user entered it), recolor his edge to green.
        if firstPostB == convo.firstPost:
            color = 'green'

        edges.append(Edge(emailB, emailA, color))
        num_edges += 1

    # If we didn't draw any edges, at least draw an edge from the
    # main user to us.
    if num_edges == 0:
        eprint("Adding an edge from the main user.")
        edges.append(Edge(args.mainUsersEmail, emailA, 'black'))

print('digraph G {')
print(' graph[overlap=false, splines=ortho, fontname="Roboto"];')
print(' node[shape=box, style=rounded, fontname="Roboto", fontsize=10];')
print(' edge[fontname="Roboto"];')

for edge in edges:
    print(' "%s" -> "%s" [color=%s]' % (edge.src, edge.dest, edge.color))

print('}')

eprint('Done.')
