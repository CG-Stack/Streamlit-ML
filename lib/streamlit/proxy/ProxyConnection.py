# -*- coding: future_fstrings -*-

"""Stores information shared by both local_connections and
client_connections related to a particular report."""

# Python 2/3 compatibility
from __future__ import print_function, division, unicode_literals, absolute_import
from streamlit.compatibility import setup_2_3_shims
setup_2_3_shims(globals())

import json
import os
import subprocess

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from streamlit import config
from streamlit.ReportQueue import ReportQueue
from streamlit import protobuf

from streamlit.logger import get_logger
from streamlit.util import get_local_id
LOGGER = get_logger()

class ProxyConnection(object):
    """Represents a connection.

    IMPORTANT: Always call .close() on this object when you're done with it.
    """

    def __init__(self, new_report_msg, name):
        # The uuid of this report.
        self.id = new_report_msg.id

        # The current working directory from which this report was launched.
        self.cwd = new_report_msg.cwd

        # The command and command-line arguments used to launch this connection.
        self.command_line = list(new_report_msg.command_line)

        # Full path of the file that cause this connection to be initiated.
        self.source_file_path = new_report_msg.source_file_path

        # The name for this report.
        self.name = name

        # When the local connection ends, this flag becomes false.
        self._has_local = True

        # Before recieving connection and the the timeout hits, the connection
        # is in a "grace period" in which it can't be deregistered.
        self._in_grace_period = True

        # A master queue for incoming deltas, replicated for each connection.
        self._master_queue = ReportQueue()

        # Each connection additionally gets its own queue.
        self._client_queues = []

        # File system observer.
        self._fs_observer = self._initialize_fs_observer_with_fallback()

    def close(self):
        """Close the connection."""
        LOGGER.info('Closing ProxyConnection')

        if self._fs_observer is not None:
            LOGGER.info('Closing file system observer')
            self._fs_observer.stop()

            # Wait til thread terminates.
            # TODO(thiago): This could be slow. Is this really needed?
            self._fs_observer.join(timeout=5)

    def _initialize_fs_observer_with_fallback(self):
        """Start the filesystem observer.

        Fall back to non-recursive mode if needed.
        """
        do_watch = config.get_option('proxy.watchFileSystem')

        if not do_watch:
            return None

        recursive = config.get_option('proxy.watchUpdatesRecursively')
        patterns = config.get_option('proxy.watchPatterns')
        ignore_patterns = config.get_option('proxy.ignorePatterns')

        path_to_observe = os.path.dirname(self.source_file_path)

        fs_observer = _initialize_fs_observer(
            fn_to_run=self._on_fs_event,
            path_to_observe=path_to_observe,
            recursive=recursive,
            patterns=patterns,
            ignore_patterns=ignore_patterns,
        )

        # If the previous command errors out, try a fallback command that is
        # less useful but also less likely to fail.
        if fs_observer is None and recursive is True:
            fs_observer = _initialize_fs_observer(
                fn_to_run=self._on_fs_event,
                path_to_observe=path_to_observe,
                recursive=False,  # No longer recursive.
                patterns=patterns,
                ignore_patterns=ignore_patterns,
            )

        return fs_observer

    # TODO(thiago): Open this using a separate thread, for speed.
    def _on_fs_event(self, event):
        LOGGER.info(f'File system event: [{event.event_type}] {event.src_path}')

        # TODO(thiago): Move this and similar code from ClientWebSocket.py to a
        # single file.
        process = subprocess.Popen(self.command_line, cwd=self.cwd)

        # Required! Otherwise we end up with defunct processes.
        # (See ps -Al | grep python)
        process.wait()

    def finished_local_connection(self):
        """Removes the flag indicating an active local connection."""
        self._has_local = False
        self._master_queue.close()
        for queue in self._client_queues:
            queue.close()

    def end_grace_period(self):
        """Inicates that the grace period is over and the connection can be
        closed when it no longer has any local or client connections."""
        self._in_grace_period = False

    def can_be_deregistered(self):
        """Indicates whether we can deregister this connection."""
        has_clients = len(self._client_queues) > 0
        return not (self._in_grace_period or self._has_local or has_clients)

    def enqueue(self, delta):
        """Stores the delta in the master queue and transmits to all clients
        via client_queues."""
        self._master_queue(delta)
        for queue in self._client_queues:
            queue(delta)

    def add_client_queue(self):
        """Adds a queue for a new client by cloning the master queue."""
        self.end_grace_period()
        new_queue = self._master_queue.clone()
        self._client_queues.append(new_queue)
        return new_queue

    def remove_client_queue(self, queue):
        """Removes the client queue. Returns True iff the client queue list is
        empty."""
        self._client_queues.remove(queue)

    def serialize_report_to_files(self):
        """Returns a list of pairs to be serialized of the form:
            [
                (filename_1, data_1),
                (filename_2, data_2), etc..
            ]
        """
        # Get the deltas. Need to clone() becuase get_deltas() clears the queue.
        deltas = self._master_queue.clone().get_deltas()
        local_id = str(get_local_id())
        manifest = dict(
            name = self.name,
            local_id = local_id,
            nDeltas = len(deltas)
        )
        return \
            [(f'reports/{self.id}/manifest.json', json.dumps(manifest))] + \
            [(f'reports/{self.id}/{idx}.delta', delta.SerializeToString())
                for idx, delta in enumerate(deltas)]


def _initialize_fs_observer(path_to_observe, recursive, **kwargs):
    """Initialize the filesystem observer.

    Parameters
    ----------
    path_to_observe : string
        The file system path to observe.
    recursive : boolean
        If true, will observe path_to_observe and its subfolders recursively.

    Passes kwargs to FSEventHandler.

    """
    handler = FSEventHandler(**kwargs)

    fs_observer = Observer()
    fs_observer.schedule(handler, path_to_observe, recursive)

    LOGGER.info(f'Will observe file system at: {path_to_observe}')

    try:
        fs_observer.start()
        LOGGER.info(f'Observing file system at: {path_to_observe}')
    except OSError as e:
        fs_observer = None
        LOGGER.error(f'Could not start file system observer: {e}')

    return fs_observer


class FSEventHandler(PatternMatchingEventHandler):
    """Calls a function whenever a watched file changes."""

    def __init__(self, fn_to_run, *args, **kwargs):
        """Constructor.

        Parameters
        ----------
        fn_to_run : function
            The function to call whenever a watched file changes. Takes the
            FileSystemEvent as a parameter.

        Also accepts the following parameters from PatternMatchingEventHandler:
        patterns and ignore_patterns.

        More information at https://pythonhosted.org/watchdog/api.html#watchdog.events.PatternMatchingEventHandler
        """
        LOGGER.info(f'Starting FSEventHandler with args={args} kwargs={kwargs}')

        super(FSEventHandler, self).__init__(*args, **kwargs)
        self._fn_to_run = fn_to_run

    def on_any_event(self, event):
        """Catch-all event handler.

        See https://pythonhosted.org/watchdog/api.html#watchdog.events.FileSystemEventHandler.on_any_event

        Parameters
        ----------
        event : FileSystemEvent
            The event object representing the file system event.

        """
        self._fn_to_run(event)
