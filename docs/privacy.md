# Privacy and event use

Photographing participants is optional.  The opening screen provides Einstein
as a direct non-camera route, and the bundled Cat and radio-source examples can
also be selected by a facilitator.

For a camera capture:

- the browser requests camera access only after **Start camera** is pressed;
- a frame is captured only after the capture button is pressed;
- the frame is sent only to the Python server on the same computer;
- the server is restricted to loopback addresses;
- the application processes the frame in memory and does not write it to disk;
- there is no application endpoint that uploads a visitor frame to an external
  service;
- the browser retains the most recent capture in memory so a facilitator can
  switch sources and return to it;
- **New image** clears the retained capture from the application state.

This technical design does not replace event policy.  Before deployment, the
activity should still be checked against the current University/event
organiser's photography, privacy and safeguarding guidance.  The software
supports alternatives such as using a teacher/demonstrator volunteer or
avoiding live photography entirely.
