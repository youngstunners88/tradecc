"""Outbound notification transports.

Separate from `core` because these reach the network, and separate from
`execution` because nothing here can move money. `core.alerts` defines the
sink protocol; this package implements it.
"""
