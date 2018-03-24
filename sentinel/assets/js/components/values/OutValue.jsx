import React from "react";
import PropTypes from "prop-types";
import ToggleButton from 'react-toggle-button';

export class OutValue extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            value: this.props.value
        };
        this.handleChange = this.handleChange.bind(this);
        this.sendChange = this.sendChange.bind(this);
    }

    getPattern() {
        if(this.props.format === "number" || this.props.format === "number+units") {
            return "^[0-9]+$";
        } else if (this.props.format === "bool") {
            return "^(true|false|0|1)$";
        } else {
            return ".*";
        }
    }

    handleChange(event) {
        this.setState({value: event.target.value});
    }

    sendChange(value) {
        if(value === null) {
            if (this.props.format === 'string') {
                value = this.state.value;
            } else {
                value = JSON.parse(this.state.value);
            }
        }
        this.props.updateValue(value);
    }

    render(){
        if (this.props.format === "bool") {
            return (
                <ToggleButton
                  value={ this.state.value || false }
                  onToggle={(value) => {
                    this.setState({value: !this.state.value});
                    this.sendChange(!this.state.value);
                  }} disabled={this.props.connected} />
            );
        } else {
            return (
                <div className={"input-group" + (this.props.small ? " input-group-xs" : "")}>
                    <input type="text" pattern={this.getPattern()} onChange={this.handleChange}
                           className="form-control" placeholder={this.props.value + "(current)"} aria-label="new_value"
                           aria-describedby="basic-addon2" disabled={!this.props.connected}/>
                    <div className="input-group-append input-group-btn">
                        <button onClick={this.sendChange} className="btn btn-outline-secondary" type="button" disabled={!this.props.connected}>
                            <i className="fas fa-angle-right"/></button>
                    </div>
                </div>);
        }
    }
}

OutValue.propTypes = {
    small: PropTypes.bool,
    value: PropTypes.any,
    format: PropTypes.string,
    connected: PropTypes.bool,
    updateValue: PropTypes.func
};