# NautilusTrader 1.231 request-boundary audit

Date: 2026-08-15
Scope: the bare, in-process `DataEngine` lifecycles in
`aegis_data._catalog_request` and `aegis_data.continuous_materialize`.

## Conclusion

Keep:

```python
msgbus.request(endpoint="DataEngine.request", request=request)
```

for these two NautilusTrader 1.231 Cython `DataEngine` integrations.
`DataEngine.request(request)` is a public callable handler, but it is not the
request-submission boundary: calling it directly skips the message bus's
correlation registration. A later `DataResponse` is processed by the engine,
but the request callback cannot be found and is never called.

There is no typed endpoint constant or alternate overload in the 1.231 Cython
API which performs both operations. `MessageBus.request` accepts a string
endpoint and a `Request`; `DataEngine` registers its request handler under the
literal `"DataEngine.request"`.

## Exact 1.231 lifecycle

1. `DataEngine.__init__` registers `self.request` at
   `"DataEngine.request"` on the message bus
   ([v1.231.0 source, lines 267-272](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L267-L272)).
2. `MessageBus.request(endpoint, request)` rejects duplicate request IDs,
   stores `request.callback` in `_correlation_index`, looks up the endpoint,
   and then calls its handler
   ([v1.231.0 source, lines 2617-2653](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/component.pyx#L2617-L2653)).
3. `DataEngine.request(request)` only validates and passes the request to
   `_handle_request`; it does not register the callback
   ([v1.231.0 source, lines 872-884](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L872-L884)).
4. After processing a response, the engine calls `self._msgbus.response(...)`;
   the message bus removes the callback from `_correlation_index` and invokes
   it
   ([engine response source, lines 3091-3103](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L3091-L3103),
   [message-bus response source, lines 2655-2679](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/component.pyx#L2655-L2679)).

The endpoint string is not an Aegis invention. Nautilus's own 1.231 Cython
`Actor` request methods build typed requests but ultimately submit them through
the same call in `_send_data_req`
([v1.231.0 source, lines 5011-5015](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/actor.pyx#L5011-L5015)).
The engine also uses this exact message-bus request path for its internal child,
join, continuous-future, and long requests
([examples in v1.231.0 engine source](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/data/engine.pyx#L2372-L2383)).

## Installed-version probes

The `aegis-data` environment reports `nautilus_trader.__version__ == "1.231.0"`.
Its installed method signatures are:

```text
MessageBus.request(self, endpoint, request)
DataEngine.request(self, request)
Actor.request_data(..., callback=None, ...)
Actor.request_bars(..., callback=None, ...)
```

A minimal probe used a bare `MessageBus`, `DataEngine`, and a holding
`DataClient`, then submitted the same callback-bearing `RequestData` by the two
paths. Before response:

```text
bus path:    is_pending_request(request.id) == True
direct path: is_pending_request(request.id) == False
```

After sending the same valid `DataResponse` through the registered
`DataEngine.response` endpoint:

```text
bus path:    callbacks == 1, engine responses == 1
direct path: callbacks == 0, engine responses == 1
```

This isolates the semantic difference: both paths enter the engine, but only
the message-bus path establishes response routing.

## Higher-level Actor and Strategy APIs

Context7 correctly points callers running inside an actor or strategy toward
high-level methods such as `request_data`, `request_instrument`, and
`request_bars`; the official actor documentation demonstrates that usage
([v1.231.0 actor docs](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/docs/concepts/actors.md#request-responses-vs-subscription-data)).
Those methods are the right public API for an already registered actor or
strategy. They are not a smaller replacement for Aegis's headless helper:

- a Python `Actor` must be registered with a trader and requires portfolio,
  cache, message bus, and clock facades; `register_base` is explicitly a system
  method
  ([v1.231.0 source, lines 691-732](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/actor.pyx#L691-L732));
- its completion callback receives a request ID, while historical records are
  delivered through actor historical-data handlers; this is a different
  interface from Aegis's generic raw `RequestData`/`DataResponse` factory;
- internally the actor still uses the same string-routed `MessageBus.request`,
  so adding an actor solely to hide the literal would add lifecycle and adapter
  code without eliminating the underlying mechanism.

## Native Rust `DataActor` is a different stack

Version 1.231 also contains a newer native Rust `DataActor`. Its typed request
implementation registers a response handler by request ID and sends a typed
`DataCommand::Request`
([v1.231.0 Rust source, lines 4890-4929](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/crates/common/src/actor/data_actor.rs#L4890-L4929)).
That is the genuinely typed design, but it is not an alternate entry point on
the Cython `DataEngine` used by these Aegis modules. In the installed 1.231
wheel, the documented `from nautilus_trader.common import DataActor` raises
`ImportError`; the class is reachable only through the low-level
`nautilus_trader.core.nautilus_pyo3` module. It also requires native actor
registration and uses the native/global message-bus stack.

Adopting it would therefore be a separate engine/lifecycle migration, not a
one-line correction to the current request call. It should not be mixed into
this cleanup without an end-to-end compatibility spike for catalog
registration, custom data, continuous-future parameters, client adapters, and
Python callback behavior.

## Alternatives considered

| Alternative | Result |
| --- | --- |
| `engine.request(request)` | Invalid: skips correlation/callback registration. |
| `msgbus.send("DataEngine.request", request)` | Invalid: point-to-point send also skips request correlation registration. |
| Manually mutate `msgbus._correlation_index`, then call the engine | Invalid: private state and a reimplementation of `MessageBus.request`. |
| Instantiate a Python `Actor` only to call `request_*` | Semantically possible with a full trader/portfolio lifecycle, but deeper and still string-routed internally. |
| Use native Rust/PyO3 `DataActor` | Potential future migration target, not compatible as a direct Cython `DataEngine` replacement. |

## Recommendation

Treat `MessageBus.request(endpoint="DataEngine.request", request=request)` as
the supported low-level request boundary for a bare Cython `DataEngine` in
NautilusTrader 1.231. Keep it centralized in Aegis's small engine-owning
modules. Do not wrap the endpoint in an Aegis abstraction merely to hide the
string: Nautilus itself owns and repeats this address, and no 1.231 public
constant exists.

If eliminating string endpoints remains a goal, scope a separate native
`DataActor`/native engine migration spike. The acceptance criterion must be the
same callback/correlation probe plus Aegis catalog and continuous-future
contract tests; direct `DataEngine.request()` is not that migration.
