package domain

import "errors"

var (
	ErrNotFound          = errors.New("resource not found")
	ErrInvalidTransition = errors.New("invalid incident state transition")
	ErrUnauthorized      = errors.New("unauthorized request")
	ErrUpstream          = errors.New("upstream bridge unavailable")
	ErrValidation        = errors.New("validation error")
)
